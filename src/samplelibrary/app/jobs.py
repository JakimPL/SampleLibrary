from __future__ import annotations

import logging
import signal
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.config import LibraryConfig
from samplecore.models.base import FROZEN
from samplecore.progress import ProgressReport, read_progress
from samplelibrary.app.processes import child_environment
from samplelibrary.pipeline.events import (
    AttemptEnded,
    AttemptStarted,
    PipelineEvent,
    RunEnded,
    RunRefused,
    RunStarted,
    StepDecided,
    read_events,
)
from samplelibrary.pipeline.layout import PipelineLayout, RunPaths
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict

JOB_LOG_NAME: Final[str] = "pipeline.log"
LOGS_DIRECTORY_NAME: Final[str] = "logs"
LOG_TAIL_LINES: Final[int] = 20

_logger = logging.getLogger(__name__)


class JobAlreadyRunningError(Exception):
    """Raised when a build is asked for while another one runs."""


@unique
class BuildTarget(StrEnum):
    """What a person asks the application to build: the catalog of their folders, or the whole library with its cloud."""

    CATALOG = "catalog"
    ALL = "all"


@unique
class JobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@unique
class StepState(StrEnum):
    """Where one step of a build stands, as a person reads it off the build's checklist."""

    WAITING = "waiting"
    UP_TO_DATE = "up to date"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepView(BaseModel):
    model_config = FROZEN

    name: str
    state: StepState
    progress: ProgressReport | None


class JobView(BaseModel):
    """One build as the application shows it: its steps in order, the running step's progress, and why it failed."""

    model_config = FROZEN

    target: BuildTarget
    status: JobStatus
    started_at: datetime
    ended_at: datetime | None
    steps: tuple[StepView, ...]
    problem: str | None
    log_tail: tuple[str, ...]


class Job:
    """One `samplelibrary pipeline run` the application started, and the run directory it writes into."""

    def __init__(
        self, *, target: BuildTarget, process: subprocess.Popen[bytes], layout: PipelineLayout, known_runs: set[Path]
    ) -> None:
        self.target = target
        self.started_at = datetime.now(UTC)
        self.ended_at: datetime | None = None
        self.canceled = False
        self._process = process
        self._layout = layout
        self._known_runs = known_runs
        self._run: RunPaths | None = None

    @property
    def is_running(self) -> bool:
        running = self._process.poll() is None
        if not running and self.ended_at is None:
            self.ended_at = datetime.now(UTC)
        return running

    def cancel(self) -> None:
        """Ask the run to stop the way Ctrl+C asks it, letting the running step keep the work it committed."""
        if not self.is_running:
            return
        self.canceled = True
        if sys.platform == "win32":
            self._process.terminate()
            return
        self._process.send_signal(signal.SIGINT)

    def wait(self) -> None:
        self._process.wait()

    def view(self, log_path: Path) -> JobView:
        run = self._run_paths()
        events = tuple(read_events(run.events)) if run is not None else ()
        steps = _step_views(events, run)
        return JobView(
            target=self.target,
            status=self._status(events),
            started_at=self.started_at,
            ended_at=self.ended_at,
            steps=steps,
            problem=_problem(events),
            log_tail=_log_tail(run, steps, log_path),
        )

    def _status(self, events: tuple[PipelineEvent, ...]) -> JobStatus:
        if self.is_running:
            return JobStatus.RUNNING
        if self.canceled:
            return JobStatus.CANCELED
        ended = [event.outcome for event in events if isinstance(event, RunEnded)]
        if self._process.returncode == 0 and ended == [RunOutcome.COMPLETED]:
            return JobStatus.COMPLETED
        return JobStatus.FAILED

    def _run_paths(self) -> RunPaths | None:
        """The run directory this job's run opened: the first one to appear under the runs folder after it started."""
        if self._run is None and self._layout.runs.is_dir():
            new_runs = sorted(path for path in self._layout.runs.iterdir() if path not in self._known_runs)
            if new_runs:
                directory = new_runs[0]
                self._run = RunPaths(directory=directory, run_id=directory.name)
        return self._run


class JobRunner:
    """Starts the builds a person asks for, one at a time, and reports the latest one."""

    def __init__(self, *, config_path: Path, pipeline_command: tuple[str, ...]) -> None:
        self._config_path = config_path
        self._pipeline_command = pipeline_command
        self._job: Job | None = None
        self._log_path: Path | None = None

    def start(self, config: LibraryConfig, target: BuildTarget) -> None:
        """Start building ``target`` for the library ``config`` names.

        Raises:
            JobAlreadyRunningError: a build already runs.
        """
        if self._job is not None and self._job.is_running:
            raise JobAlreadyRunningError("A build is already running. Wait for it to finish or cancel it.")
        layout = PipelineLayout(config.library_root)
        known_runs = set(layout.runs.iterdir()) if layout.runs.is_dir() else set()
        self._log_path = config.library_root / LOGS_DIRECTORY_NAME / JOB_LOG_NAME
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.info("Building %s for the library at %s.", target.value, config.library_root)
        with self._log_path.open("ab") as log:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                (*self._pipeline_command, target.value),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=child_environment(self._config_path),
            )
        self._job = Job(target=target, process=process, layout=layout, known_runs=known_runs)

    def cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()

    def view(self) -> JobView | None:
        if self._job is None or self._log_path is None:
            return None
        return self._job.view(self._log_path)

    def stop(self) -> None:
        """Stop a running build and wait for it, as the application closes."""
        if self._job is not None:
            self._job.cancel()
            self._job.wait()


def _step_views(events: tuple[PipelineEvent, ...], run: RunPaths | None) -> tuple[StepView, ...]:
    """Each step of the run in its order, in the state its latest event puts it."""
    order: tuple[str, ...] = ()
    states: dict[str, StepState] = {}
    for event in events:
        match event:
            case RunStarted():
                order = event.steps
            case AttemptStarted():
                states[event.step] = StepState.RUNNING
            case AttemptEnded():
                states[event.step] = StepState.DONE if event.outcome is AttemptOutcome.COMPLETED else StepState.FAILED
            case StepDecided():
                states[event.step] = _decided_state(event.verdict)
            case _:
                pass
    return tuple(
        StepView(
            name=step,
            state=states.get(step, StepState.WAITING),
            progress=(
                read_progress(run.progress(step))
                if run is not None and states.get(step) in (StepState.RUNNING, StepState.DONE, StepState.FAILED)
                else None
            ),
        )
        for step in order
    )


def _decided_state(verdict: StepVerdict) -> StepState:
    """The state a run's decision puts a step in; a step decided to run is announced just before its attempt starts."""
    match verdict:
        case StepVerdict.SATISFIED:
            return StepState.UP_TO_DATE
        case StepVerdict.RAN:
            return StepState.RUNNING
        case StepVerdict.RESEALED:
            return StepState.DONE
        case StepVerdict.REFUSED:
            return StepState.FAILED
        case StepVerdict.NOT_REACHED:
            return StepState.SKIPPED


def _problem(events: tuple[PipelineEvent, ...]) -> str | None:
    for event in events:
        match event:
            case RunRefused():
                return event.reason
            case AttemptEnded() if event.outcome is not AttemptOutcome.COMPLETED:
                return f"Step '{event.step}' ended: {event.outcome.value}."
            case _:
                pass
    return None


def _log_tail(run: RunPaths | None, steps: tuple[StepView, ...], job_log: Path) -> tuple[str, ...]:
    """The last lines of the failed step's log, or of the build's own log when no step failed."""
    failed = next((step.name for step in steps if step.state is StepState.FAILED), None)
    path = run.log(failed) if run is not None and failed is not None else job_log
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8", errors="replace") as log:
        return tuple(line.rstrip("\n") for line in deque(log, maxlen=LOG_TAIL_LINES))
