from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import Field

from samplecloud.evaluation.settings import DEFAULT_PROBE_COUNT
from samplecloud.evaluation.settings import DEFAULT_RANDOM_SEED as DEFAULT_EVALUATION_SEED
from samplecloud.evaluation.settings import EvaluationScope
from samplecloud.features import readable_pending_count
from samplecloud.hearing import hearing_for
from samplecore.models.experiment import ExperimentKey, Reading
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.sample_audio import readable_membership_digest
from sampledescriptor.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE
from sampledescriptor.descriptors.shape import DEFAULT_WIDTH
from sampledescriptor.geometry import DEFAULT_ANCHOR, Anchor
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import PretrainedDescriptor, PretrainedDescriptorMissingError, pretrained_descriptor
from sampledescriptor.registries import DEFAULT_CANONICALIZER_NAME
from sampledescriptor.training.descriptor.cache import (
    DEFAULT_RETUNED_VIEW_COUNT,
    DEFAULT_VIEW_RANGE_SEMITONES,
    DESCRIPTION_FILE_NAME,
    grid_cache_directory,
)
from sampledescriptor.training.descriptor.settings import (
    DEFAULT_DESCRIPTOR_BATCH_SIZE,
    DEFAULT_DESCRIPTOR_EPOCHS,
    DEFAULT_DESCRIPTOR_LEARNING_RATE,
    DEFAULT_DISTILLATION_WEIGHT,
    DEFAULT_LABEL_HOLDOUT_SHARE,
    DEFAULT_LABEL_WEIGHT,
    DEFAULT_LABELED_PER_BATCH,
    DEFAULT_RETUNING_WEIGHT,
)
from sampledescriptor.training.run.paths import RunFamily, finished_record_path, resume_path, run_directory
from sampledescriptor.training.run.settings import DEFAULT_RANDOM_SEED
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.results import input_digest
from samplelibrary.pipeline.settings import DescriptorSource, StepSettings
from samplelibrary.pipeline.steps.catalog import EQUIVALENCE, MODULES, NOTES, RELINK, SAMPLE_FILES
from samplelibrary.pipeline.steps.kinds import (
    DerivedExperimentStep,
    FileArtifactStep,
    GrowingExperimentStep,
    Inputs,
    Step,
    StepRefused,
    TrainingRecords,
    directory_artifact_is_complete,
    local_artifact_is_complete,
)
from samplelibrary.pipeline.steps.listening import TEACHER, TEACHER_KEY
from samplelibrary.pipeline.steps.shared import (
    LABELS,
    PARAMETERS,
    READABLE_SAMPLES,
    TrainingRunSettings,
    filed_experiment,
    operational_flags,
    sealed_content,
    training_run_flags,
    vectors_digest,
)

GRID_CACHE: Final[str] = "grid-cache"
DESCRIPTOR: Final[str] = "descriptor"
EMBEDDING: Final[str] = "embedding"
COMPLETION: Final[str] = "completion"
EVALUATION: Final[str] = "evaluation"
MODULE_EVALUATION: Final[str] = "module-evaluation"
GRID_CACHE_PREFIX: Final[str] = "descriptor"
DESCRIPTOR_RUN_PREFIX: Final[str] = "descriptor-run"
SEALED_DESCRIPTOR_PREFIX: Final[str] = "descriptor"
LEARNED_KEY_PREFIX: Final[str] = "learned"
SEALED_CHARACTERS: Final[int] = 16
GRID_CACHE_INPUT: Final[str] = "grid cache"
TEACHER_VECTORS: Final[str] = "teacher vectors"
PRETRAINED_INPUT: Final[str] = "pretrained descriptor"
DESCRIPTOR_INPUT: Final[str] = "descriptor"
EXPERIMENT: Final[str] = "experiment"
VECTORS: Final[str] = "vectors"
RELATIONS: Final[str] = "relations"
PLAYBACK_RATES: Final[str] = "playback rates"
OWNED_OUTPUTS: Final[tuple[str, ...]] = (
    f"cache/grids/{GRID_CACHE_PREFIX}-*",
    f"models/descriptors/{SEALED_DESCRIPTOR_PREFIX}-*",
    f"runs/descriptor/{DESCRIPTOR_RUN_PREFIX}-*",
)


class GridCacheSettings(StepSettings):
    """What the grid cache is read under: the axis, how finely it is kept, and the retuned views each sample gets."""

    canonicalizer: str = DEFAULT_CANONICALIZER_NAME
    anchor: Anchor = DEFAULT_ANCHOR
    bands_per_semitone: int = Field(default=DESCRIPTOR_BANDS_PER_SEMITONE, ge=1)
    views: int = Field(default=DEFAULT_RETUNED_VIEW_COUNT, ge=0)
    range: float = DEFAULT_VIEW_RANGE_SEMITONES
    seed: int = DEFAULT_RANDOM_SEED


class DescriptorSettings(TrainingRunSettings):
    """How the descriptor is taught: its training run, its width, and what each part of the loss says."""

    epochs: int = Field(default=DEFAULT_DESCRIPTOR_EPOCHS, ge=1)
    batch: int = Field(default=DEFAULT_DESCRIPTOR_BATCH_SIZE, ge=1)
    learning_rate: float = DEFAULT_DESCRIPTOR_LEARNING_RATE
    width: int = Field(default=DEFAULT_WIDTH, ge=1)
    distillation_weight: float = DEFAULT_DISTILLATION_WEIGHT
    retuning_weight: float = DEFAULT_RETUNING_WEIGHT
    label_weight: float = DEFAULT_LABEL_WEIGHT
    label_holdout: float = DEFAULT_LABEL_HOLDOUT_SHARE
    labeled_per_batch: int = Field(default=DEFAULT_LABELED_PER_BATCH, ge=1)


class EvaluationStepSettings(StepSettings):
    """How a descriptor is scored: how many samples are retuned for retrieval, and the seed every draw uses."""

    probes: int = Field(default=DEFAULT_PROBE_COUNT, ge=1)
    seed: int = DEFAULT_EVALUATION_SEED


def descriptor_steps(source: DescriptorSource) -> tuple[Step, ...]:
    """The learned descriptor from its grid cache to the experiment describing every readable sample, and its scores.

    The cache and the training run are named by what they were built from, the finished model is
    kept under its own content, and the experiment is named by that model and the cache it
    described, so a library that stands still rebuilds none of them and one that grew rebuilds each.
    A library taking the bundled descriptor stores that model in place of training one, under the
    name its bytes give it.
    """
    return (
        FileArtifactStep(
            name=GRID_CACHE,
            requires=(MODULES, SAMPLE_FILES),
            inputs=_grid_cache_inputs,
            artifact=_grid_cache_directory,
            command=_cache_command,
            complete=directory_artifact_is_complete(DESCRIPTION_FILE_NAME),
        ),
        _descriptor_step(source),
        DerivedExperimentStep(
            name=EMBEDDING,
            requires=(DESCRIPTOR, GRID_CACHE),
            inputs=_embedding_inputs,
            key=lambda context, digest: f"{LEARNED_KEY_PREFIX}-{digest}",
            command=_embed_command,
        ),
        GrowingExperimentStep(
            name=COMPLETION,
            requires=(EMBEDDING, MODULES, SAMPLE_FILES),
            key=learned_key,
            command=lambda context: ("cloud", "embed", "--key", learned_key(context), "--extract-only")
            + operational_flags(context, workers=False, device=True),
            pending=_nominal_pending,
            inputs=lambda context: {
                READABLE_SAMPLES: readable_membership_digest(context.connection),
                EXPERIMENT: learned_key(context),
            },
        ),
        _evaluation(EVALUATION, EvaluationScope.CATALOG),
        _evaluation(MODULE_EVALUATION, EvaluationScope.MODULES),
    )


def _descriptor_step(source: DescriptorSource) -> FileArtifactStep:
    match source:
        case DescriptorSource.TRAINED:
            return FileArtifactStep(
                name=DESCRIPTOR,
                requires=(GRID_CACHE, TEACHER, RELINK),
                inputs=_descriptor_inputs,
                artifact=_descriptor_run_model,
                command=_train_command,
                complete=local_artifact_is_complete,
                training=_descriptor_training,
                sealed_as=_sealed_descriptor,
            )
        case DescriptorSource.PRETRAINED:
            return FileArtifactStep(
                name=DESCRIPTOR,
                requires=(),
                inputs=_descriptor_inputs,
                artifact=_descriptor_run_model,
                command=_adopt_command,
                complete=local_artifact_is_complete,
                sealed_as=_sealed_descriptor,
            )


def learned_key(context: PipelineContext) -> ExperimentKey:
    """The key of the experiment the descriptor and the cache it read make together."""
    return f"{LEARNED_KEY_PREFIX}-{input_digest(_embedding_inputs(context))}"


def _grid_cache_settings(context: PipelineContext) -> GridCacheSettings:
    """The grid cache's settings: the configured ones, or for the bundled descriptor the axis it reads.

    The bundled descriptor describes only the stored grid of each sample, so its cache keeps no
    retuned views, which only training reads.
    """
    match context.settings.descriptor_source:
        case DescriptorSource.TRAINED:
            return context.settings.settings_for(GRID_CACHE, GridCacheSettings)
        case DescriptorSource.PRETRAINED:
            manifest = _pretrained().manifest
            return GridCacheSettings(
                canonicalizer=manifest.canonicalizer,
                anchor=manifest.anchor,
                bands_per_semitone=manifest.bands_per_semitone,
                views=0,
            )


def _grid_cache_inputs(context: PipelineContext) -> Inputs:
    return {
        READABLE_SAMPLES: readable_membership_digest(context.connection),
        PARAMETERS: _grid_cache_settings(context).parameters_digest,
    }


def _grid_cache_name(digest: str) -> str:
    return f"{GRID_CACHE_PREFIX}-{digest}"


def _grid_cache_directory(context: PipelineContext, digest: str) -> Path:
    return grid_cache_directory(context.config.library_root, name=_grid_cache_name(digest))


def _current_grid_cache(context: PipelineContext) -> Path:
    return _grid_cache_directory(context, input_digest(_grid_cache_inputs(context)))


# pylint: disable-next=unused-argument
def _cache_command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
    settings = _grid_cache_settings(context)
    return (
        "descriptor",
        "cache-grids",
        "--cache",
        artifact.name,
        "--canonicalizer",
        settings.canonicalizer,
        "--anchor",
        settings.anchor.value,
        "--bands-per-semitone",
        str(settings.bands_per_semitone),
        "--views",
        str(settings.views),
        "--range",
        str(settings.range),
        "--seed",
        str(settings.seed),
        *operational_flags(context, workers=True, device=False),
    )


def _descriptor_settings(context: PipelineContext) -> DescriptorSettings:
    return context.settings.settings_for(DESCRIPTOR, DescriptorSettings)


def _descriptor_inputs(context: PipelineContext) -> Inputs:
    """What the descriptor is built from: what training reads, or the bundled model's own bytes."""
    match context.settings.descriptor_source:
        case DescriptorSource.TRAINED:
            return {
                GRID_CACHE_INPUT: sealed_content(_current_grid_cache(context)),
                TEACHER_VECTORS: vectors_digest(context, TEACHER_KEY),
                LABELS: PostgresSampleAnnotationRepository(context.connection).label_digest(),
                PARAMETERS: _descriptor_settings(context).parameters_digest,
            }
        case DescriptorSource.PRETRAINED:
            return {PRETRAINED_INPUT: _pretrained().content}


def _pretrained() -> PretrainedDescriptor:
    """The bundled descriptor.

    Raises:
        StepRefused: this installation carries no bundled descriptor.
    """
    try:
        return pretrained_descriptor()
    except PretrainedDescriptorMissingError as error:
        raise StepRefused(str(error)) from error


# pylint: disable-next=unused-argument
def _adopt_command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
    return ("descriptor", "adopt", "--descriptor", artifact.stem)


def _descriptor_run_name(digest: str) -> str:
    return f"{DESCRIPTOR_RUN_PREFIX}-{digest}"


def _descriptor_run_model(context: PipelineContext, digest: str) -> Path:
    return descriptor_path(context.config.library_root, name=_descriptor_run_name(digest))


def _descriptor_training(context: PipelineContext, digest: str) -> TrainingRecords:
    root = context.config.library_root
    name = _descriptor_run_name(digest)
    return TrainingRecords(
        directory=run_directory(root, family=RunFamily.DESCRIPTOR, name=name),
        resume_point=resume_path(root, family=RunFamily.DESCRIPTOR, name=name),
        finished=finished_record_path(root, family=RunFamily.DESCRIPTOR, name=name),
    )


def _sealed_descriptor(context: PipelineContext, content: str) -> Path:
    return descriptor_path(
        context.config.library_root, name=f"{SEALED_DESCRIPTOR_PREFIX}-{content[:SEALED_CHARACTERS]}"
    )


def _train_command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
    settings = _descriptor_settings(context)
    return (
        "descriptor",
        "train",
        "--cache",
        _current_grid_cache(context).name,
        "--teacher-experiment",
        str(filed_experiment(context, TEACHER_KEY)),
        "--descriptor",
        artifact.stem,
        "--width",
        str(settings.width),
        "--distillation-weight",
        str(settings.distillation_weight),
        "--retuning-weight",
        str(settings.retuning_weight),
        "--label-weight",
        str(settings.label_weight),
        "--label-holdout",
        str(settings.label_holdout),
        "--labeled-per-batch",
        str(settings.labeled_per_batch),
        *training_run_flags(context, settings, resume=resume),
    )


def _current_descriptor_content(context: PipelineContext) -> str:
    return sealed_content(_descriptor_run_model(context, input_digest(_descriptor_inputs(context))))


def _embedding_inputs(context: PipelineContext) -> Inputs:
    return {
        DESCRIPTOR_INPUT: _current_descriptor_content(context),
        GRID_CACHE_INPUT: sealed_content(_current_grid_cache(context)),
    }


def _embed_command(context: PipelineContext, key: ExperimentKey) -> tuple[str, ...]:
    descriptor = _sealed_descriptor(context, _current_descriptor_content(context))
    return (
        "descriptor",
        "embed",
        "--cache",
        _current_grid_cache(context).name,
        "--descriptor",
        descriptor.stem,
        "--key",
        key,
        *operational_flags(context, workers=False, device=True),
    )


def _nominal_pending(context: PipelineContext, experiment_id: int) -> int:
    return readable_pending_count(
        context.connection, experiment_id, hearing=hearing_for(context.connection, Reading.NOMINAL)
    )


def _evaluation(name: str, scope: EvaluationScope) -> FileArtifactStep:
    """One scoring of the learned experiment, over every sample it describes or over the samples modules hold."""

    def settings(context: PipelineContext) -> EvaluationStepSettings:
        return context.settings.settings_for(name, EvaluationStepSettings)

    def inputs(context: PipelineContext) -> Inputs:
        return {
            EXPERIMENT: learned_key(context),
            VECTORS: vectors_digest(context, learned_key(context)),
            RELATIONS: PostgresSampleRelationRepository(context.connection).membership_digest(),
            LABELS: PostgresSampleAnnotationRepository(context.connection).label_digest(),
            PLAYBACK_RATES: PostgresSamplePlaybackRateRepository(context.connection).rate_digest(),
            PARAMETERS: settings(context).parameters_digest,
        }

    # pylint: disable-next=unused-argument
    def command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
        chosen = settings(context)
        return (
            "cloud",
            "evaluate",
            "--experiment-id",
            str(filed_experiment(context, learned_key(context))),
            "--scope",
            scope.value,
            "--output",
            str(artifact),
            "--probes",
            str(chosen.probes),
            "--seed",
            str(chosen.seed),
            *operational_flags(context, workers=False, device=True),
        )

    report: Callable[[PipelineContext, str], Path] = lambda context, digest: context.layout.evaluations / (
        f"{scope.value}-{digest}.json"
    )
    return FileArtifactStep(
        name=name,
        requires=(COMPLETION, EQUIVALENCE, NOTES, RELINK),
        inputs=inputs,
        artifact=report,
        command=command,
        complete=local_artifact_is_complete,
    )
