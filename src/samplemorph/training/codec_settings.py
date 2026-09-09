from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from samplemorph.codecs.conditioned_model import DEFAULT_CODEC_WIDTH, DEFAULT_RESIDUAL_SIZE
from samplemorph.training.codec_losses import CodecLossWeights
from samplemorph.training.run_settings import RunSettings

DEFAULT_CODEC_EPOCHS: Final[int] = 20
DEFAULT_CODEC_BATCH_SIZE: Final[int] = 32
DEFAULT_CODEC_LEARNING_RATE: Final[float] = 3e-4
DEFAULT_PRIOR_WARMUP_STEPS: Final[int] = 2_000
DEFAULT_CODEC_VALIDATION_SHARE: Final[float] = 0.05


def default_run_settings() -> RunSettings:
    """The run shape a codec is driven by when nothing else is asked: a larger network, fewer wider steps."""
    return RunSettings(
        epochs=DEFAULT_CODEC_EPOCHS, batch_size=DEFAULT_CODEC_BATCH_SIZE, learning_rate=DEFAULT_CODEC_LEARNING_RATE
    )


@dataclass(frozen=True)
class CodecTrainingSettings:
    """What a conditioned codec is taught with, beside how the run that teaches it is driven.

    The prior's weight climbs from nothing to its full value over `prior_warmup_steps`, so the
    decoder learns to reconstruct before the residual is asked to stay near the prior; a prior
    applied from the first step is what makes a residual carry nothing at all.
    """

    run: RunSettings = field(default_factory=default_run_settings)
    weights: CodecLossWeights = field(default_factory=CodecLossWeights)
    residual_size: int = DEFAULT_RESIDUAL_SIZE
    width: int = DEFAULT_CODEC_WIDTH
    prior_warmup_steps: int = DEFAULT_PRIOR_WARMUP_STEPS
    validation_share: float = DEFAULT_CODEC_VALIDATION_SHARE

    def __post_init__(self) -> None:
        if not 0.0 < self.validation_share < 1.0:
            raise ValueError(f"the held-out share lies strictly between 0 and 1, got {self.validation_share}")
        if self.prior_warmup_steps < 0:
            raise ValueError(f"the prior's warm-up is a count of steps, got {self.prior_warmup_steps}")

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return self.run.as_parameters() | {
            "residual_size": str(self.residual_size),
            "width": str(self.width),
            "reconstruction_weight": str(self.weights.reconstruction),
            "prior_weight": str(self.weights.prior),
            "cycle_weight": str(self.weights.cycle),
            "prior_warmup_steps": str(self.prior_warmup_steps),
            "validation_share": str(self.validation_share),
        }
