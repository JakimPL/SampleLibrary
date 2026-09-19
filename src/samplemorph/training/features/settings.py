from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from samplemorph.features.shape import DEFAULT_FEATURE_WIDTH, DEFAULT_LATENT_SIZE
from samplemorph.training.run_settings import RunSettings
from samplemorph.training.splits import DEFAULT_VALIDATION_SHARE

DEFAULT_FEATURE_EPOCHS: Final[int] = 20
DEFAULT_FEATURE_BATCH_SIZE: Final[int] = 64
DEFAULT_FEATURE_LEARNING_RATE: Final[float] = 1e-4
DEFAULT_CRITIC_MIX: Final[float] = 0.2


def default_run_settings() -> RunSettings:
    """The run shape a feature model is driven by when nothing else is asked, the one the interpolation critic was published with."""
    return RunSettings(
        epochs=DEFAULT_FEATURE_EPOCHS,
        batch_size=DEFAULT_FEATURE_BATCH_SIZE,
        learning_rate=DEFAULT_FEATURE_LEARNING_RATE,
    )


@dataclass(frozen=True)
class FeatureTrainingSettings:
    """What a feature autoencoder is taught with, beside how the run that teaches it is driven.

    `critic_weight` is how much the critic's reading of the autoencoder's latent interpolants says
    in its loss; at 0 the critic still learns, which measures how plainly the interpolants show,
    and the autoencoder learns to reconstruct alone. `critic_mix` is the share of a sound mixed
    into its own reconstruction for the critic to read as a sound, which holds the critic's answer
    near 0 wherever the autoencoder reconstructs well. `validation_share` of the cached samples is
    held out, whole equivalence classes at a time.

    Raises:
        ValueError: the critic weight is negative, or a share lies outside its bounds.
    """

    critic_weight: float
    run: RunSettings = field(default_factory=default_run_settings)
    latent_size: int = DEFAULT_LATENT_SIZE
    width: int = DEFAULT_FEATURE_WIDTH
    critic_mix: float = DEFAULT_CRITIC_MIX
    validation_share: float = DEFAULT_VALIDATION_SHARE

    def __post_init__(self) -> None:
        if self.critic_weight < 0.0:
            raise ValueError(f"the critic weight must be at least 0, got {self.critic_weight}")
        if not 0.0 <= self.critic_mix <= 1.0:
            raise ValueError(f"the critic's mix lies between 0 and 1, got {self.critic_mix}")
        if not 0.0 < self.validation_share < 1.0:
            raise ValueError(f"the validation share lies strictly between 0 and 1, got {self.validation_share}")

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return self.run.as_parameters() | {
            "critic_weight": str(self.critic_weight),
            "critic_mix": str(self.critic_mix),
            "latent_size": str(self.latent_size),
            "width": str(self.width),
            "validation_share": str(self.validation_share),
        }
