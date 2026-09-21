from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from samplecore.storage.atomic import write_bytes_atomically
from samplelibrary.pipeline.artifacts import SIDECAR_SUFFIX, ScratchIntent, remove_path
from samplelibrary.pipeline.context import RunSession
from samplelibrary.pipeline.events import AttemptEnded, AttemptStarted, ScratchCompleted, ScratchStarted, Sinks
from samplelibrary.pipeline.execution import Attempt, record_attempt, run_step_command
from samplelibrary.pipeline.layout import PipelineLayout

RESET_STEP: Final[str] = "reset"
RESET_COMMAND: Final[tuple[str, ...]] = ("reset", "--confirm")
SEARCHED_DIRECTORIES: Final[tuple[str, ...]] = ("cache", "models", "runs", "pipeline")

_logger = logging.getLogger(__name__)


def start_from_scratch(session: RunSession, sinks: Sinks, owned_outputs: tuple[str, ...]) -> Attempt | None:
    """Empty the catalog and everything the pipeline built, so every step has all its work to do.

    The intent is recorded before anything goes and removed once everything has, so a run stopped
    partway through finishes the emptying before it builds anything. Hand labels stay, as they do
    through any reset, and so does everything under the library root the pipeline never sealed.
    Answers the reset's attempt where it ended some other way than completed.
    """
    layout = session.context.layout
    _record_intent(layout)
    sinks.emit(ScratchStarted())
    sinks.emit(
        AttemptStarted(
            step=RESET_STEP,
            argv=RESET_COMMAND,
            log=str(session.run.log(RESET_STEP)),
            scope=session.context.scope_name(RESET_STEP),
        )
    )
    attempt = run_step_command(session, step=RESET_STEP, command=RESET_COMMAND, follow=False)
    record_attempt(session.run.attempts, attempt)
    sinks.emit(AttemptEnded(step=RESET_STEP, outcome=attempt.outcome, exit_status=attempt.exit_status))
    if not attempt.completed:
        return attempt

    removed = remove_pipeline_outputs(layout, owned_outputs)
    layout.scratch_intent.unlink(missing_ok=True)
    sinks.emit(ScratchCompleted(removed=tuple(str(path) for path in removed)))
    return None


def scratch_is_unfinished(layout: PipelineLayout) -> bool:
    """Whether an earlier run began emptying this library and never finished."""
    return layout.scratch_intent.is_file()


def remove_pipeline_outputs(layout: PipelineLayout, owned_outputs: tuple[str, ...]) -> tuple[Path, ...]:
    """Delete everything the pipeline built under this library, and the records describing it.

    What the steps own goes by the patterns they name, a build stopped partway included, and anything
    else the pipeline sealed goes along with its sidecar. The store of extracted audio and a person's
    own files stay.
    """
    removed: list[Path] = []
    for pattern in owned_outputs:
        for path in sorted(layout.library_root.glob(pattern)):
            removed.extend(remove_path(path))
    for directory in SEARCHED_DIRECTORIES:
        root = layout.library_root / directory
        if not root.is_dir():
            continue
        for sidecar in sorted(root.rglob(f"*{SIDECAR_SUFFIX}")):
            artifact = sidecar.with_name(sidecar.name.removesuffix(SIDECAR_SUFFIX))
            removed.extend(remove_path(artifact))
            removed.extend(remove_path(sidecar))
    for record in sorted(layout.steps.glob("*.json")):
        removed.extend(remove_path(record))
    removed.extend(remove_path(layout.evaluations))
    return tuple(removed)


def _record_intent(layout: PipelineLayout) -> None:
    intent = ScratchIntent(started_at=datetime.now(UTC))
    write_bytes_atomically(layout.scratch_intent, intent.model_dump_json().encode("utf-8"))
