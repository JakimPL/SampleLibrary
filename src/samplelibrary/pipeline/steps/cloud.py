from __future__ import annotations

from typing import Final

from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository, PostgresCloudPromotionRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.steps.catalog import MODULES
from samplelibrary.pipeline.steps.descriptor import COMPLETION, VECTORS, learned_key
from samplelibrary.pipeline.steps.kinds import Inputs, PassStep, PointerStep, Step
from samplelibrary.pipeline.steps.shared import operational_flags, vectors_digest

CLOUD: Final[str] = "cloud"
MODULE_PLACEHOLDERS: Final[str] = "module-placeholders"


def cloud_steps() -> tuple[Step, ...]:
    """The cloud a viewer sees, laid out from the learned experiment, and the modules placed beside it."""
    return (
        PointerStep(
            name=CLOUD,
            requires=(COMPLETION,),
            inputs=lambda context: {VECTORS: vectors_digest(context, learned_key(context))},
            satisfied=_cloud_shows_the_learned_experiment,
            command=lambda context: ("cloud", "embed", "--key", learned_key(context))
            + operational_flags(context, workers=False, device=True),
            outputs=_shown,
        ),
        PassStep(name=MODULE_PLACEHOLDERS, requires=(MODULES,), command=lambda context: ("cloud", "placeholders")),
    )


def _cloud_shows_the_learned_experiment(context: PipelineContext) -> bool:
    """Whether the cloud shows the learned experiment, with a point for every sample it describes."""
    filed = PostgresExperimentRepository(context.connection).get_by_key(learned_key(context))
    promotion = PostgresCloudPromotionRepository(context.connection).current()
    if filed is None or promotion is None or promotion.experiment_id != filed.id:
        return False
    described = PostgresSampleFeatureVectorRepository(context.connection).heard_rates_for_experiment(filed.id).keys()
    placed = {coordinate.sample_hash for coordinate in PostgresCloudCoordinateRepository(context.connection).list_all()}
    return set(described) == placed


def _shown(context: PipelineContext) -> Inputs:
    return {"experiment": learned_key(context)}
