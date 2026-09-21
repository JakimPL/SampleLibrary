from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from samplelibrary.pipeline.graph import ALL_TARGET, StepGraph
from samplelibrary.pipeline.settings import StepSettings
from samplelibrary.pipeline.steps import descriptor
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
from samplelibrary.pipeline.steps.cloud import CLOUD, MODULE_PLACEHOLDERS, cloud_steps
from samplelibrary.pipeline.steps.descriptor import (
    DESCRIPTOR,
    EVALUATION,
    GRID_CACHE,
    MODULE_EVALUATION,
    DescriptorSettings,
    EvaluationStepSettings,
    GridCacheSettings,
    descriptor_steps,
)
from samplelibrary.pipeline.steps.listening import CATEGORIES, CategorySettings, listening_steps

CATALOG_TARGET: Final[str] = "catalog"
CLOUD_TARGET: Final[str] = "cloud"
CATALOG_STEPS: Final[tuple[str, ...]] = (
    LABELS,
    MODULES,
    SAMPLE_FILES,
    NOTES,
    THUMBNAILS,
    EQUIVALENCE,
    RELINK,
)
CLOUD_STEPS: Final[tuple[str, ...]] = (CATEGORIES, EVALUATION, MODULE_EVALUATION, CLOUD, MODULE_PLACEHOLDERS)
STEP_SETTINGS: Final[Mapping[str, type[StepSettings]]] = {
    CATEGORIES: CategorySettings,
    GRID_CACHE: GridCacheSettings,
    DESCRIPTOR: DescriptorSettings,
    EVALUATION: EvaluationStepSettings,
    MODULE_EVALUATION: EvaluationStepSettings,
}


def library_graph() -> StepGraph:
    """Every step that builds this library, the targets a run names them by, and the outputs they own."""
    steps = (*catalog_steps(), *listening_steps(), *descriptor_steps(), *cloud_steps())
    return StepGraph(
        steps=steps,
        targets={
            CATALOG_TARGET: CATALOG_STEPS,
            CLOUD_TARGET: CLOUD_STEPS,
            ALL_TARGET: tuple(step.name for step in steps),
        },
        owned_outputs=descriptor.OWNED_OUTPUTS,
    )


def settings_model(step: str) -> type[StepSettings]:
    """The settings one step reads from its own table."""
    return STEP_SETTINGS.get(step, StepSettings)
