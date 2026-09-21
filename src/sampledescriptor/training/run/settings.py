from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DEFAULT_EPOCHS: Final[int] = 20
DEFAULT_BATCH_SIZE: Final[int] = 32
DEFAULT_LEARNING_RATE: Final[float] = 2e-4
DEFAULT_WORKER_COUNT: Final[int] = 8
DEFAULT_RANDOM_SEED: Final[int] = 0
GRADIENT_CLIP: Final[float] = 1.0

TrainingPrecision = Literal["32-true", "16-mixed", "bf16-mixed"]
TRAINING_PRECISIONS: Final[tuple[TrainingPrecision, ...]] = ("32-true", "16-mixed", "bf16-mixed")
DEFAULT_PRECISION: Final[TrainingPrecision] = "32-true"
DEFAULT_ACCELERATOR: Final[str] = "cuda"


@dataclass(frozen=True)
class RunSettings:
    """How one training run is driven, whatever it trains: its length, its pace, and its machine.

    `precision` names the arithmetic a step is computed in, in the trainer's own vocabulary:
    ``32-true`` throughout, or ``16-mixed`` to carry the products at half precision while the
    weights stay whole. A 16-bit sample leaves room for either, so which one a run uses is a
    question of speed and memory rather than of what the audio can carry. `accelerator` names the
    device the trainer runs on, in its vocabulary too.
    """

    epochs: int = DEFAULT_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    learning_rate: float = DEFAULT_LEARNING_RATE
    worker_count: int = DEFAULT_WORKER_COUNT
    precision: TrainingPrecision = DEFAULT_PRECISION
    accelerator: str = DEFAULT_ACCELERATOR
    random_seed: int = DEFAULT_RANDOM_SEED

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return {
            "epochs": str(self.epochs),
            "batch_size": str(self.batch_size),
            "learning_rate": str(self.learning_rate),
            "worker_count": str(self.worker_count),
            "precision": self.precision,
            "accelerator": self.accelerator,
            "random_seed": str(self.random_seed),
        }
