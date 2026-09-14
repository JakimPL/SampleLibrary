from __future__ import annotations

from typing import Final

from samplelibrary.pipeline.graph import ALL_TARGET, StepGraph
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


def library_graph() -> StepGraph:
    """Every step that builds this library, and the targets a run names them by."""
    steps = catalog_steps()
    return StepGraph(
        steps=steps,
        targets={CATALOG_TARGET: CATALOG_STEPS, ALL_TARGET: tuple(step.name for step in steps)},
    )
