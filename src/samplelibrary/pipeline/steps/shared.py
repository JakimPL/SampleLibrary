from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import Field

from samplecore.models.experiment import ExperimentKey
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplelibrary.pipeline.artifacts import read_sidecar
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.settings import StepSettings
from samplelibrary.pipeline.steps.kinds import StepRefused
from samplemorph.training.run_settings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_LEARNING_RATE,
    DEFAULT_PRECISION,
    DEFAULT_RANDOM_SEED,
)

READABLE_SAMPLES: Final[str] = "readable samples"
PARAMETERS: Final[str] = "parameters"
LABELS: Final[str] = "labels"


def vectors_digest(context: PipelineContext, key: ExperimentKey) -> str:
    """Which samples the experiment under this key describes and at which rates, or its absence where none is filed."""
    filed = PostgresExperimentRepository(context.connection).get_by_key(key)
    if filed is None:
        return f"no experiment under {key}"
    return PostgresSampleFeatureVectorRepository(context.connection).membership_digest(filed.id)


def filed_experiment(context: PipelineContext, key: ExperimentKey) -> int:
    """The id of the experiment filed under this key, which a later step's command names.

    Raises:
        StepRefused: no experiment is filed under the key.
    """
    filed = PostgresExperimentRepository(context.connection).get_by_key(key)
    if filed is None:
        raise StepRefused(f"no experiment is filed under {key}")
    return filed.id


def sealed_content(artifact: Path) -> str:
    """What a sealed artifact holds, or its absence where nothing is sealed under that name."""
    sidecar = read_sidecar(artifact)
    return f"nothing sealed as {artifact.name}" if sidecar is None else sidecar.content


def operational_flags(context: PipelineContext, *, workers: bool, device: bool) -> tuple[str, ...]:
    """The machine's own settings a command takes, which name nothing a step builds."""
    flags: list[str] = []
    if workers and context.settings.workers is not None:
        flags.extend(["--workers", str(context.settings.workers)])
    if device:
        flags.extend(["--device", context.settings.device])
    return tuple(flags)


class TrainingRunSettings(StepSettings):
    """What every training step takes alike: how long and how fast it trains, in what arithmetic, and from which seed."""

    epochs: int = Field(default=DEFAULT_EPOCHS, ge=1)
    batch: int = Field(default=DEFAULT_BATCH_SIZE, ge=1)
    learning_rate: float = DEFAULT_LEARNING_RATE
    precision: str = DEFAULT_PRECISION
    seed: int = DEFAULT_RANDOM_SEED


def training_run_flags(context: PipelineContext, settings: TrainingRunSettings, *, resume: bool) -> tuple[str, ...]:
    """The flags every training command shares, with the machine's own and a resume where the run stopped short."""
    return (
        "--epochs",
        str(settings.epochs),
        "--batch",
        str(settings.batch),
        "--learning-rate",
        str(settings.learning_rate),
        "--precision",
        settings.precision,
        "--seed",
        str(settings.seed),
        *operational_flags(context, workers=True, device=True),
        *(("--resume",) if resume else ()),
    )
