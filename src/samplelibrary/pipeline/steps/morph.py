from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import Field

from samplecore.storage.sample_audio import readable_membership_digest
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.results import input_digest
from samplelibrary.pipeline.settings import StepSettings
from samplelibrary.pipeline.steps.catalog import MODULES, SAMPLE_FILES
from samplelibrary.pipeline.steps.kinds import (
    FileArtifactStep,
    Inputs,
    PointerStep,
    Step,
    TrainingRecords,
    local_artifact_is_complete,
)
from samplelibrary.pipeline.steps.shared import (
    PARAMETERS,
    READABLE_SAMPLES,
    TrainingRunSettings,
    sealed_content,
    training_run_flags,
)
from samplemorph.commands.fit import DEFAULT_FIT_SAMPLE_COUNT
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor
from samplemorph.model_paths import restorer_path
from samplemorph.model_store import model_path
from samplemorph.published import (
    holds_published,
    published_codec_path,
    published_restorer_path,
    read_published,
)
from samplemorph.registries import DEFAULT_CANONICALIZER_NAME
from samplemorph.training.principal_components import DEFAULT_LATENT_SIZE
from samplemorph.training.restorer_settings import (
    DEFAULT_RESTORER_BATCH_SIZE,
    DEFAULT_RESTORER_EPOCHS,
    DEFAULT_RESTORER_LEARNING_RATE,
    DEFAULT_RESTORER_PRECISION,
)
from samplemorph.training.run_paths import RunFamily, finished_record_path, resume_path, run_directory
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED
from samplemorph.training.settings import DEFAULT_CROP_FRAMES
from samplemorph.vocoders.restorer_shape import DEFAULT_CHANNELS

MORPH_CODEC: Final[str] = "morph-codec"
RESTORER: Final[str] = "restorer"
MORPH_MODELS: Final[str] = "morph-models"
CODEC_PREFIX: Final[str] = "principal_components"
RESTORER_PREFIX: Final[str] = "restorer"
CODEC_INPUT: Final[str] = "codec"
RESTORER_INPUT: Final[str] = "restorer"
OWNED_OUTPUTS: Final[tuple[str, ...]] = (
    f"models/{CODEC_PREFIX}-*",
    f"models/{RESTORER_PREFIX}-*",
    f"runs/restorer/{RESTORER_PREFIX}-*",
    "models/published.json",
    "models/principal_components.npz",
    "models/restorer.pt",
)


class CodecSettings(StepSettings):
    """What the codec is fitted under: its axis, how many components it keeps, and the draw it reads."""

    canonicalizer: str = DEFAULT_CANONICALIZER_NAME
    anchor: Anchor = DEFAULT_ANCHOR
    latent_size: int = Field(default=DEFAULT_LATENT_SIZE, ge=1)
    samples: int = Field(default=DEFAULT_FIT_SAMPLE_COUNT, ge=1)
    seed: int = DEFAULT_RANDOM_SEED


class RestorerSettings(TrainingRunSettings):
    """How the restorer is taught: its axis, its capacity, its crops and its training run."""

    epochs: int = Field(default=DEFAULT_RESTORER_EPOCHS, ge=1)
    batch: int = Field(default=DEFAULT_RESTORER_BATCH_SIZE, ge=1)
    learning_rate: float = DEFAULT_RESTORER_LEARNING_RATE
    precision: str = DEFAULT_RESTORER_PRECISION
    canonicalizer: str = DEFAULT_CANONICALIZER_NAME
    anchor: Anchor = DEFAULT_ANCHOR
    samples: int | None = Field(default=None, ge=1)
    channels: int = Field(default=DEFAULT_CHANNELS, ge=1)
    crop: int = Field(default=DEFAULT_CROP_FRAMES, ge=1)


def morph_steps() -> tuple[Step, ...]:
    """The codec and the restorer the renderer morphs through, each named by what it was built from, and their publication."""
    return (
        FileArtifactStep(
            name=MORPH_CODEC,
            requires=(MODULES, SAMPLE_FILES),
            inputs=_codec_inputs,
            artifact=lambda context, digest: model_path(context.config.library_root, name=f"{CODEC_PREFIX}-{digest}"),
            command=_fit_command,
            complete=local_artifact_is_complete,
        ),
        FileArtifactStep(
            name=RESTORER,
            requires=(MODULES, SAMPLE_FILES),
            inputs=_restorer_inputs,
            artifact=lambda context, digest: restorer_path(
                context.config.library_root, name=f"{RESTORER_PREFIX}-{digest}"
            ),
            command=_restorer_command,
            complete=local_artifact_is_complete,
            training=_restorer_training,
        ),
        PointerStep(
            name=MORPH_MODELS,
            requires=(MORPH_CODEC, RESTORER),
            inputs=_published_inputs,
            satisfied=_both_published,
            command=_publish_command,
            outputs=_published_inputs,
        ),
    )


def _codec_settings(context: PipelineContext) -> CodecSettings:
    return context.settings.settings_for(MORPH_CODEC, CodecSettings)


def _restorer_settings(context: PipelineContext) -> RestorerSettings:
    return context.settings.settings_for(RESTORER, RestorerSettings)


def _codec_inputs(context: PipelineContext) -> Inputs:
    return {
        READABLE_SAMPLES: readable_membership_digest(context.connection),
        PARAMETERS: _codec_settings(context).parameters_digest,
    }


def _restorer_inputs(context: PipelineContext) -> Inputs:
    return {
        READABLE_SAMPLES: readable_membership_digest(context.connection),
        PARAMETERS: _restorer_settings(context).parameters_digest,
    }


def _current_codec(context: PipelineContext) -> Path:
    return model_path(context.config.library_root, name=f"{CODEC_PREFIX}-{input_digest(_codec_inputs(context))}")


def _current_restorer(context: PipelineContext) -> Path:
    return restorer_path(
        context.config.library_root, name=f"{RESTORER_PREFIX}-{input_digest(_restorer_inputs(context))}"
    )


# pylint: disable-next=unused-argument
def _fit_command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
    settings = _codec_settings(context)
    return (
        "morph",
        "fit",
        "--model",
        artifact.stem,
        "--canonicalizer",
        settings.canonicalizer,
        "--anchor",
        settings.anchor.value,
        "--latent-size",
        str(settings.latent_size),
        "--samples",
        str(settings.samples),
        "--seed",
        str(settings.seed),
    )


def _restorer_training(context: PipelineContext, digest: str) -> TrainingRecords:
    root = context.config.library_root
    name = f"{RESTORER_PREFIX}-{digest}"
    return TrainingRecords(
        directory=run_directory(root, family=RunFamily.RESTORER, name=name),
        resume_point=resume_path(root, family=RunFamily.RESTORER, name=name),
        finished=finished_record_path(root, family=RunFamily.RESTORER, name=name),
    )


def _restorer_command(context: PipelineContext, artifact: Path, resume: bool) -> tuple[str, ...]:
    settings = _restorer_settings(context)
    samples = () if settings.samples is None else ("--samples", str(settings.samples))
    return (
        "morph",
        "train-restorer",
        "--restorer",
        artifact.stem,
        "--canonicalizer",
        settings.canonicalizer,
        "--anchor",
        settings.anchor.value,
        *samples,
        "--channels",
        str(settings.channels),
        "--crop",
        str(settings.crop),
        *training_run_flags(context, settings, resume=resume),
    )


def _published_inputs(context: PipelineContext) -> Inputs:
    return {
        CODEC_INPUT: sealed_content(_current_codec(context)),
        RESTORER_INPUT: sealed_content(_current_restorer(context)),
    }


def _both_published(context: PipelineContext) -> bool:
    """Whether the renderer's default models are this run's codec and restorer, standing as they were published."""
    root = context.config.library_root
    published = read_published(root)
    if published is None:
        return False
    inputs = _published_inputs(context)
    return (
        published.codec.content == inputs[CODEC_INPUT]
        and published.restorer.content == inputs[RESTORER_INPUT]
        and holds_published(published_codec_path(root), published.codec)
        and holds_published(published_restorer_path(root), published.restorer)
    )


def _publish_command(context: PipelineContext) -> tuple[str, ...]:
    return (
        "morph",
        "publish",
        "--model",
        _current_codec(context).stem,
        "--restorer",
        _current_restorer(context).stem,
    )
