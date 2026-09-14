from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from samplelibrary.pipeline.graph import ALL_TARGET, StepGraph
from samplelibrary.pipeline.settings import StepSettings
from samplelibrary.pipeline.steps.catalog import (
    EQUIVALENCE,
    LABELS,
    MODULES,
    NOTES,
    RELINK,
    SAMPLE_FILES,
    THUMBNAILS,
    catalog_steps,
)
from samplelibrary.pipeline.steps.listening import SUGGESTIONS, SuggestionSettings, listening_steps

CATALOG_TARGET: Final[str] = "catalog"
CATALOG_STEPS: Final[tuple[str, ...]] = (
    LABELS,
    MODULES,
    SAMPLE_FILES,
    NOTES,
    THUMBNAILS,
    EQUIVALENCE,
    RELINK,
)
STEP_SETTINGS: Final[Mapping[str, type[StepSettings]]] = {SUGGESTIONS: SuggestionSettings}


def library_graph() -> StepGraph:
    """Every step that builds this library, and the targets a run names them by."""
    steps = (*catalog_steps(), *listening_steps())
    return StepGraph(
        steps=steps,
        targets={CATALOG_TARGET: CATALOG_STEPS, ALL_TARGET: tuple(step.name for step in steps)},
    )


def settings_model(step: str) -> type[StepSettings]:
    """The settings one step reads from its own table."""
    return STEP_SETTINGS.get(step, StepSettings)
