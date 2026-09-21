from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
from samplelibrary.pipeline.execution import read_attempts
from samplelibrary.pipeline.layout import ATTEMPTS_FILE_NAME, PipelineLayout
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict

ABANDONED_GATE = "abandoned the gate"


@dataclass(frozen=True)
class RunObservation:
    """What one run did, read from the events it recorded rather than from anything it returned."""

    exit_status: int
    events: tuple[PipelineEvent, ...]
    recorded: tuple[PipelineEvent, ...]
    directory: Path | None

    @property
    def verdicts(self) -> dict[str, StepVerdict]:
        return {event.step: event.verdict for event in self.events if isinstance(event, StepDecided)}

    @property
    def reasons(self) -> dict[str, frozenset[str]]:
        return {event.step: frozenset(event.reasons) for event in self.events if isinstance(event, StepDecided)}

    @property
    def outcomes(self) -> dict[str, AttemptOutcome]:
        return {event.step: event.outcome for event in self.events if isinstance(event, AttemptEnded)}

    @property
    def started(self) -> tuple[str, ...]:
        return tuple(event.step for event in self.events if isinstance(event, AttemptStarted))

    @property
    def outcome(self) -> RunOutcome | None:
        ended = [event.outcome for event in self.events if isinstance(event, RunEnded)]
        return ended[-1] if ended else None

    @property
    def refusal(self) -> str | None:
        refused = [event.reason for event in self.events if isinstance(event, RunRefused)]
        return refused[-1] if refused else None

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(event.kind for event in self.events)


def observe_run(layout: PipelineLayout, events: Path, exit_status: int) -> RunObservation:
    """Read what a run did: the events a scenario's sink copied, and the record the run kept itself.

    The run's own directory is found by the identity its first event names, so a run started beside
    another is never read in its place.
    """
    copied = tuple(read_events(events))
    run_ids = [event.run_id for event in copied if isinstance(event, RunStarted)]
    directory = _run_directory(layout, run_ids[0]) if run_ids else None
    recorded = tuple(read_events(directory / "events.jsonl")) if directory is not None else ()
    return RunObservation(exit_status=exit_status, events=copied, recorded=recorded, directory=directory)


def _run_directory(layout: PipelineLayout, run_id: str) -> Path | None:
    matches = sorted(layout.runs.glob(f"*-{run_id}"))
    return matches[0] if matches else None


@dataclass(frozen=True)
class Evidence:
    """What a run left behind apart from its own account: attempts, logs and the scripted steps' ledger."""

    attempts: tuple[str, ...]
    logs: tuple[str, ...]
    ledger: tuple[str, ...]
    abandoned_gates: tuple[str, ...]


def read_evidence(observation: RunObservation, ledger: Path) -> Evidence:
    """Every step a run actually started, read from records the scheduler does not narrate."""
    directory = observation.directory
    return Evidence(
        attempts=(
            tuple(record.step for record in read_attempts(directory / ATTEMPTS_FILE_NAME))
            if directory is not None
            else ()
        ),
        logs=tuple(sorted(path.stem for path in directory.glob("*.log"))) if directory is not None else (),
        ledger=tuple(str(entry["step"]) for entry in ledger_entries(ledger)),
        abandoned_gates=tuple(
            str(entry["step"]) for entry in ledger_entries(ledger) if entry["command"] == [ABANDONED_GATE]
        ),
    )


def ledger_entries(ledger: Path) -> tuple[Mapping[str, object], ...]:
    """Every entry scripted steps appended to a ledger, in the order they started."""
    if not ledger.is_file():
        return ()
    return tuple(json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())


def ledger_commands(ledger: Path) -> dict[str, tuple[str, ...]]:
    """The words after the command's options each scripted step was handed, by step."""
    return {str(entry["step"]): tuple(str(word) for word in entry["command"]) for entry in ledger_entries(ledger)}  # type: ignore[attr-defined]


def log_tail(directory: Path | None, step: str, lines: int) -> str:
    """The last lines a step wrote to its log in a run, for a story explaining where it diverged."""
    if directory is None:
        return ""
    log = directory / f"{step}.log"
    if not log.is_file():
        return ""
    return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
