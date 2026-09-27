from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from sampledescriptor.pretrained import MISSING_RELEASE_MESSAGE, publishes_pretrained
from sampleripper.pipeline.graph import ALL_TARGET, StepGraph
from sampleripper.pipeline.settings import DESCRIPTOR_SOURCE_SETTING, DescriptorSource, StepSettings
from sampleripper.pipeline.steps import cloud, descriptor
from sampleripper.pipeline.steps.catalog import (
    EQUIVALENCE,
    LABELS,
    MODULES,
    NOTES,
    RELINK,
    SAMPLE_FILES,
    THUMBNAILS,
    catalog_steps,
)
from sampleripper.pipeline.steps.cloud import CLOUD, MODULE_CLOUD, cloud_steps
from sampleripper.pipeline.steps.descriptor import (
    DESCRIPTOR,
    EVALUATION,
    GRID_CACHE,
    MODULE_EVALUATION,
    DescriptorSettings,
    EvaluationStepSettings,
    GridCacheSettings,
    descriptor_steps,
)
from sampleripper.pipeline.steps.listening import (
    CATEGORIES,
    HEARING_TEACHER,
    TEACHER,
    CategorySettings,
    ListeningSettings,
    listening_steps,
)

CATALOG_TARGET: Final[str] = "catalog"
REMOVE_SOURCE_REMEDY: Final[str] = (
    f"Remove {DESCRIPTOR_SOURCE_SETTING} from the [pipeline] table to train one on your library."
)
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
CLOUD_STEPS: Final[tuple[str, ...]] = (CATEGORIES, EVALUATION, MODULE_EVALUATION, CLOUD, MODULE_CLOUD)
TRAINING_ONLY_STEPS: Final[frozenset[str]] = frozenset({TEACHER, EVALUATION, MODULE_EVALUATION})
STEP_SETTINGS: Final[Mapping[str, type[StepSettings]]] = {
    TEACHER: ListeningSettings,
    HEARING_TEACHER: ListeningSettings,
    CATEGORIES: CategorySettings,
    GRID_CACHE: GridCacheSettings,
    DESCRIPTOR: DescriptorSettings,
    EVALUATION: EvaluationStepSettings,
    MODULE_EVALUATION: EvaluationStepSettings,
}


def library_graph(source: DescriptorSource) -> StepGraph:
    """Every step that builds this library, the targets a run names them by, and the outputs they own.

    A library taking the pretrained descriptor holds no step that only training reads: the listening
    model's nominal reading the descriptor is taught from, and the scores of a descriptor trained here.
    Where this version of the application carries no published descriptor, the steps reading it are
    unavailable, so a run needing them refuses before its first step.
    """
    steps = tuple(
        step
        for step in (*catalog_steps(), *listening_steps(), *descriptor_steps(source), *cloud_steps())
        if source is DescriptorSource.TRAINED or step.name not in TRAINING_ONLY_STEPS
    )
    names = {step.name for step in steps}
    return StepGraph(
        steps=steps,
        targets={
            CATALOG_TARGET: CATALOG_STEPS,
            CLOUD_TARGET: tuple(name for name in CLOUD_STEPS if name in names),
            ALL_TARGET: tuple(step.name for step in steps),
        },
        owned_outputs=descriptor.OWNED_OUTPUTS + cloud.OWNED_OUTPUTS,
        unavailable=_unavailable_steps(source),
    )


def _unavailable_steps(source: DescriptorSource) -> Mapping[str, str]:
    if source is DescriptorSource.TRAINED or publishes_pretrained():
        return {}
    reason = f"{MISSING_RELEASE_MESSAGE} {REMOVE_SOURCE_REMEDY}"
    return {GRID_CACHE: reason, DESCRIPTOR: reason}


def every_step_name() -> frozenset[str]:
    """The name of every step a library may hold, whichever descriptor it takes."""
    return frozenset(step.name for step in library_graph(DescriptorSource.TRAINED).steps)


def settings_model(step: str) -> type[StepSettings]:
    """The settings one step reads from its own table."""
    return STEP_SETTINGS.get(step, StepSettings)
