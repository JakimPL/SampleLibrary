from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import FrameType
from typing import Final

from pydantic import BaseModel

from samplecore.exit_status import ExitStatus
from samplecore.models.base import FROZEN
from samplelibrary.environment import (
    CONFIG_OPTION,
    MEMORY_CAP_OPTION,
    MEMORY_SCOPE_OPTION,
    STEP_LOCK_ENVIRONMENT_VARIABLE,
)
from samplelibrary.limits.scope import MemoryScope
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.results import AttemptOutcome

INTERRUPT_STATUSES: Final[frozenset[int]] = frozenset({130, -signal.SIGINT, -signal.SIGTERM, 143, -1073741510})
KILLED_STATUSES: Final[frozenset[int]] = frozenset({137, -signal.SIGKILL})
RECORDED_PACKAGES: Final[tuple[str, ...]] = ("torch", "transformers", "librosa", "trackmod", "numpy")
TQDM_INTERVAL_SECONDS: Final[str] = "30"
CHILD_ENVIRONMENT: Final[Mapping[str, str]] = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONUTF8": "1",
    "TQDM_MININTERVAL": TQDM_INTERVAL_SECONDS,
}
CLEARED_ENVIRONMENT_PREFIXES: Final[tuple[str, ...]] = ("SAMPLELIBRARY_", "MLFLOW_")

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attempt:
    """One run of one step's command: what it ran, how it ended, and where its output went."""

    step: str
    argv: tuple[str, ...]
    outcome: AttemptOutcome
    exit_status: int
    log: Path
    started_at: datetime
    ended_at: datetime

    @property
    def completed(self) -> bool:
        return self.outcome is AttemptOutcome.COMPLETED


class AttemptRecord(BaseModel):
    """One attempt as a line of the run's own record, with what this build was when it ran."""

    model_config = FROZEN

    step: str
    argv: tuple[str, ...]
    outcome: AttemptOutcome
    exit_status: int
    log: str
    started_at: datetime
    ended_at: datetime
    revision: str | None
    packages: Mapping[str, str]


class InterruptWatch:
    """Counts the interrupts a person sends while a child runs, and stops that child on the second.

    The first interrupt lets the child end as it chooses, which is how a pass keeps the work it has
    committed; the second kills everything under the step's memory scope, and further ones do the
    same. The handlers stay installed only while a child runs, so a run outside this behaves as any
    program does.
    """

    def __init__(self, scope: MemoryScope, scope_name: str) -> None:
        self._scope = scope
        self._scope_name = scope_name
        self.count = 0
        self._previous: dict[int, object] = {}

    def __enter__(self) -> InterruptWatch:
        for number in self._watched():
            self._previous[number] = signal.getsignal(number)
            signal.signal(number, self._received)
        return self

    def __exit__(self, *exception: object) -> None:
        for number, handler in self._previous.items():
            signal.signal(number, handler)  # type: ignore[arg-type]
        self._previous.clear()

    def _watched(self) -> tuple[int, ...]:
        if sys.platform == "win32":
            return (signal.SIGINT,)
        return (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

    def _received(self, number: int, frame: FrameType | None) -> None:  # pylint: disable=unused-argument
        self.count += 1
        _logger.warning("Interrupted; %s.", "stopping the step" if self.count > 1 else "waiting for the step to end")
        if self.count > 1:
            self._scope.terminate(self._scope_name)


def run_step_command(context: PipelineContext, *, step: str, command: tuple[str, ...], follow: bool) -> Attempt:
    """Run one step's command as a process of its own, under its memory ceiling and its own lock.

    The child writes straight into the step's log, so nothing of a long pass waits on a pipe, and a
    person following the run reads that file. Its environment carries the configuration this run
    snapshotted and the lock its step is held under, and nothing this process was started with that
    would point it at another library.
    """
    ceiling = context.settings.ceiling_for(step)
    scope_name = context.scope_name(step)
    log = context.run.log(step)
    argv = tuple(
        [
            *context.resolver.program(command),
            CONFIG_OPTION,
            str(context.run.config_snapshot),
            MEMORY_CAP_OPTION,
            str(ceiling),
            MEMORY_SCOPE_OPTION,
            scope_name,
            *command,
        ]
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    with log.open("ab") as stream, InterruptWatch(context.scope, scope_name) as interrupts:
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            argv,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=_child_environment(step_lock=scope_name),
            start_new_session=sys.platform != "win32",
        )
        if follow:
            _logger.info("Following %s.", log)
        status = process.wait()
        outcome = _outcome_of(status, interrupted=interrupts.count > 0, capped=ceiling.enforced)
    return Attempt(
        step=step,
        argv=argv,
        outcome=outcome,
        exit_status=status,
        log=log,
        started_at=started_at,
        ended_at=datetime.now(UTC),
    )


def record_attempt(path: Path, attempt: Attempt) -> None:
    """Append one attempt to the run's record, on a line of its own."""
    record = AttemptRecord(
        step=attempt.step,
        argv=attempt.argv,
        outcome=attempt.outcome,
        exit_status=attempt.exit_status,
        log=str(attempt.log),
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        revision=_repository_revision(),
        packages=_package_versions(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{record.model_dump_json()}\n")
        file.flush()


def read_attempts(path: Path) -> tuple[AttemptRecord, ...]:
    """Every attempt a run recorded, skipping a last line a stopped run left half written."""
    if not path.is_file():
        return ()
    records: list[AttemptRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(AttemptRecord.model_validate_json(line))
        except ValueError:
            continue
    return tuple(records)


def _outcome_of(status: int, *, interrupted: bool, capped: bool) -> AttemptOutcome:
    """What an exit status means, read beside what this run knows about how the child was treated."""
    if status == ExitStatus.COMPLETED:
        return AttemptOutcome.COMPLETED
    if interrupted or status in INTERRUPT_STATUSES:
        return AttemptOutcome.INTERRUPTED
    if status == ExitStatus.MEMORY_CAP_REACHED or (capped and status in KILLED_STATUSES):
        return AttemptOutcome.MEMORY_CAP_REACHED
    if status == ExitStatus.REFUSED:
        return AttemptOutcome.REFUSED
    return AttemptOutcome.FAILED


def _child_environment(*, step_lock: str) -> dict[str, str]:
    """What a step's process starts with: this environment, cleared of what would point it elsewhere."""
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith(CLEARED_ENVIRONMENT_PREFIXES)
    }
    environment.update(CHILD_ENVIRONMENT)
    environment[STEP_LOCK_ENVIRONMENT_VARIABLE] = step_lock
    return environment


def _package_versions() -> dict[str, str]:
    """What this build reads its heavy work through, so a recorded attempt says what produced it."""
    versions: dict[str, str] = {}
    for package in RECORDED_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


def _repository_revision() -> str | None:
    """The commit this project runs from, where it runs from a checkout at all."""
    try:
        finished = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
        )
    except OSError:
        return None
    return finished.stdout.strip() or None
