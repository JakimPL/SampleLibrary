from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field, TypeAdapter

from samplecore.models.base import FROZEN
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict

_logger = logging.getLogger(__name__)


class _Event(BaseModel):
    model_config = FROZEN

    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunStarted(_Event):
    """A run begins over the targets a command line named."""

    kind: Literal["run started"] = "run started"
    run_id: str
    targets: tuple[str, ...]
    steps: tuple[str, ...]


class LockAcquired(_Event):
    """This run holds the library's pipeline lock, so no other run acts on it meanwhile."""

    kind: Literal["lock acquired"] = "lock acquired"


class LockLost(_Event):
    """The connection holding the pipeline lock went, so the run stops rather than acting unheld."""

    kind: Literal["lock lost"] = "lock lost"


class ScratchStarted(_Event):
    """A run starting from scratch begins emptying the catalog and the outputs the pipeline named."""

    kind: Literal["scratch started"] = "scratch started"


class ScratchCompleted(_Event):
    """The catalog and the pipeline's own outputs are gone, so every step has everything to do."""

    kind: Literal["scratch completed"] = "scratch completed"
    removed: tuple[str, ...]


class RedoApplied(_Event):
    """A step's own output was dropped, so the run builds it again."""

    kind: Literal["redo applied"] = "redo applied"
    step: str


class InputsEvaluated(_Event):
    """What a step reads now, component by component, before the run decides anything about it."""

    kind: Literal["inputs evaluated"] = "inputs evaluated"
    step: str
    inputs: Mapping[str, str]
    digest: str


class StepDecided(_Event):
    """What the run decided about a step, and which of its inputs moved since it last finished."""

    kind: Literal["step decided"] = "step decided"
    step: str
    verdict: StepVerdict
    reasons: tuple[str, ...]


class AttemptStarted(_Event):
    """A step's command is running, under the log and the memory scope named here."""

    kind: Literal["attempt started"] = "attempt started"
    step: str
    argv: tuple[str, ...]
    log: str
    scope: str


class AttemptEnded(_Event):
    """How a step's command ended, and what it held at its peak where the system reports it."""

    kind: Literal["attempt ended"] = "attempt ended"
    step: str
    outcome: AttemptOutcome
    exit_status: int


class StepSealed(_Event):
    """A step's output is complete and bound to the inputs it was built from."""

    kind: Literal["step sealed"] = "step sealed"
    step: str
    outputs: Mapping[str, str]


class RunRefused(_Event):
    """A run declined to start, naming what a person settles first."""

    kind: Literal["run refused"] = "run refused"
    reason: str


class RunEnded(_Event):
    """How the run ended, over the steps it decided."""

    kind: Literal["run ended"] = "run ended"
    outcome: RunOutcome


PipelineEvent = Annotated[
    RunStarted
    | LockAcquired
    | LockLost
    | ScratchStarted
    | ScratchCompleted
    | RedoApplied
    | InputsEvaluated
    | StepDecided
    | AttemptStarted
    | AttemptEnded
    | StepSealed
    | RunRefused
    | RunEnded,
    Field(discriminator="kind"),
]
EVENT_ADAPTER: TypeAdapter[PipelineEvent] = TypeAdapter(PipelineEvent)
EVENTS_FILE_NAME = "events.jsonl"


class EventSink(Protocol):
    """Takes every event a run emits, in the order the run emits them."""

    def emit(self, event: PipelineEvent) -> None: ...


class EventFile:
    """Every event of a run, one JSON object per line, flushed as it is written.

    The file is what `status` and a reader of a finished run read, so it is written after the effect
    each event reports and never buffered past the line it is on.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def emit(self, event: PipelineEvent) -> None:
        with self._path.open("a", encoding="utf-8") as file:
            file.write(f"{event.model_dump_json()}\n")
            file.flush()


class ConsoleLog:
    """The events a person watching a run reads, as plain log lines."""

    def emit(self, event: PipelineEvent) -> None:
        match event:
            case RunStarted():
                _logger.info("Run %s over %s.", event.run_id, ", ".join(event.targets))
            case StepDecided():
                reasons = f" because {', '.join(sorted(event.reasons))}" if event.reasons else ""
                _logger.info("%-20s %s%s", event.step, event.verdict.value, reasons)
            case AttemptStarted():
                _logger.info("%-20s running, logging to %s", event.step, event.log)
            case AttemptEnded():
                _logger.info("%-20s %s (exit %d)", event.step, event.outcome.value, event.exit_status)
            case RunRefused():
                _logger.error("Ran nothing: %s.", event.reason)
            case RunEnded():
                _logger.info("Run %s.", event.outcome.value)
            case _:
                _logger.debug("%s", event.kind)


class Sinks:
    """Every sink a run reports through, each taking the events in turn."""

    def __init__(self, sinks: Sequence[EventSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(self, event: PipelineEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


def read_events(path: Path) -> Iterator[PipelineEvent]:
    """Every event a run recorded, skipping a last line a stopped run left half written."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield EVENT_ADAPTER.validate_json(line)
        except ValueError:
            continue


def parse_event(line: str) -> PipelineEvent:
    """One recorded event, read back as the event it was."""
    return EVENT_ADAPTER.validate_json(line)


def event_json(event: PipelineEvent) -> str:
    """One event as the line a run records it on."""
    return json.dumps(json.loads(event.model_dump_json()), separators=(",", ":"))
