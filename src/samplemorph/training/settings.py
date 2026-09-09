from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from samplemorph.training.phase_data import DEFAULT_WORKER_COUNT
from samplemorph.training.phase_dataset import DEFAULT_CROP_FRAMES
from samplemorph.training.phase_losses import LossWeights
from samplemorph.vocoders.phase_model import DEFAULT_CHANNELS

DEFAULT_BATCH_SIZE: Final[int] = 32
DEFAULT_EPOCHS: Final[int] = 20
DEFAULT_LEARNING_RATE: Final[float] = 2e-4
DEFAULT_RANDOM_SEED: Final[int] = 0
GRADIENT_CLIP: Final[float] = 1.0

TrainingPrecision = Literal["32-true", "16-mixed", "bf16-mixed"]
TRAINING_PRECISIONS: Final[tuple[TrainingPrecision, ...]] = ("32-true", "16-mixed", "bf16-mixed")
DEFAULT_PRECISION: Final[TrainingPrecision] = "32-true"


@dataclass(frozen=True)
class TrainingSettings:
    """How one training run is shaped, recorded beside the weights it produces.

    `precision` names the arithmetic a step is computed in, in the trainer's own vocabulary:
    ``32-true`` throughout, or ``16-mixed`` to carry the products at half precision while the
    weights stay whole. A 16-bit sample leaves room for either, so which one a run uses is a
    question of speed and memory rather than of what the audio can carry.
    """

    epochs: int = DEFAULT_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    learning_rate: float = DEFAULT_LEARNING_RATE
    crop_frames: int = DEFAULT_CROP_FRAMES
    channels: int = DEFAULT_CHANNELS
    worker_count: int = DEFAULT_WORKER_COUNT
    precision: TrainingPrecision = DEFAULT_PRECISION
    random_seed: int = DEFAULT_RANDOM_SEED
    weights: LossWeights = field(default_factory=LossWeights)

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return {
            "epochs": str(self.epochs),
            "batch_size": str(self.batch_size),
            "learning_rate": str(self.learning_rate),
            "crop_frames": str(self.crop_frames),
            "channels": str(self.channels),
            "worker_count": str(self.worker_count),
            "precision": self.precision,
            "random_seed": str(self.random_seed),
            "gradient_weight": str(self.weights.gradient),
            "spectral_weight": str(self.weights.spectral),
        }
