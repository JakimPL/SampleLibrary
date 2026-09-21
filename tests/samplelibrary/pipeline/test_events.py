from __future__ import annotations

from pathlib import Path

from samplelibrary.pipeline.events import (
    AttemptEnded,
    EventFile,
    RunStarted,
    Sinks,
    StepDecided,
    read_events,
)
from samplelibrary.pipeline.results import AttemptOutcome, StepVerdict


def _events() -> tuple[RunStarted, StepDecided, AttemptEnded]:
    return (
        RunStarted(run_id="abcd1234", targets=("catalog",), steps=("modules",)),
        StepDecided(step="modules", verdict=StepVerdict.RAN, reasons=("sample membership",)),
        AttemptEnded(step="modules", outcome=AttemptOutcome.COMPLETED, exit_status=0),
    )


def test_every_event_a_run_records_reads_back_as_the_event_it_was(tmp_path: Path) -> None:
    written = _events()
    file = EventFile(tmp_path / "events.jsonl")
    for event in written:
        file.emit(event)

    assert tuple(read_events(tmp_path / "events.jsonl")) == written


def test_a_line_a_stopped_run_left_half_written_is_passed_over(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    file = EventFile(path)
    for event in _events():
        file.emit(event)
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"kind":"run ended","outc')

    assert len(tuple(read_events(path))) == len(_events())


def test_a_run_with_no_events_yet_reads_as_none(tmp_path: Path) -> None:
    assert tuple(read_events(tmp_path / "absent.jsonl")) == ()


def test_every_sink_takes_every_event_in_turn(tmp_path: Path) -> None:
    taken: list[str] = []

    class Recording:
        def emit(self, event: object) -> None:
            taken.append(type(event).__name__)

    sinks = Sinks([Recording(), Recording()])
    for event in _events():
        sinks.emit(event)

    assert taken.count("RunStarted") == 2
    assert len(taken) == 2 * len(_events())
