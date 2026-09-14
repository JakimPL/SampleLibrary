from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from samplecore.storage.atomic import write_bytes_atomically
from samplelibrary.pipeline.artifacts import SIDECAR_SUFFIX, ScratchIntent, remove_path
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.events import ScratchCompleted, ScratchStarted, Sinks
from samplelibrary.pipeline.execution import Attempt, record_attempt, run_step_command
from samplelibrary.pipeline.layout import PipelineLayout

RESET_STEP: Final[str] = "reset"
SEARCHED_DIRECTORIES: Final[tuple[str, ...]] = ("cache", "models", "runs", "pipeline")

_logger = logging.getLogger(__name__)


def start_from_scratch(context: PipelineContext, sinks: Sinks) -> Attempt | None:
    """Empty the catalog and everything the pipeline built, so every step has all its work to do.

    The intent is recorded before anything goes and removed once everything has, so a run stopped
    partway through finishes the emptying before it builds anything. Hand labels stay, as they do
    through any reset, and so does everything under the library root the pipeline never sealed.
    """
    sinks.emit(ScratchStarted())
    _record_intent(context.layout)
    attempt = run_step_command(context, step=RESET_STEP, command=("reset", "--confirm"), follow=False)
    record_attempt(context.run.attempts, attempt)
    if not attempt.completed:
        return attempt

    removed = remove_pipeline_outputs(context.layout)
    context.layout.scratch_intent.unlink(missing_ok=True)
    sinks.emit(ScratchCompleted(removed=tuple(str(path) for path in removed)))
    return None


def scratch_is_unfinished(layout: PipelineLayout) -> bool:
    """Whether an earlier run began emptying this library and never finished."""
    return layout.scratch_intent.is_file()


def remove_pipeline_outputs(layout: PipelineLayout) -> tuple[Path, ...]:
    """Delete everything the pipeline sealed under this library, and the records describing it.

    What the pipeline built is exactly what it sealed, so the sidecars name it: each one goes along
    with the artifact beside it. The store of extracted audio and a person's own files are untouched.
    """
    removed: list[Path] = []
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
