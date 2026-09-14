from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from samplemorph.descriptors.descriptor_shape import DEFAULT_WIDTH
from samplemorph.training.refusals import TrainingRefused
from samplemorph.training.run_settings import RunSettings

DEFAULT_DESCRIPTOR_EPOCHS: Final[int] = 40
DEFAULT_DESCRIPTOR_BATCH_SIZE: Final[int] = 128
DEFAULT_DESCRIPTOR_LEARNING_RATE: Final[float] = 1e-3
DEFAULT_LABEL_HOLDOUT_SHARE: Final[float] = 0.25
DEFAULT_LABELED_PER_BATCH: Final[int] = 32
DEFAULT_VALIDATION_GALLERY: Final[int] = 1000
DEFAULT_DISTILLATION_WEIGHT: Final[float] = 1.0
DEFAULT_RETUNING_WEIGHT: Final[float] = 0.5
DEFAULT_LABEL_WEIGHT: Final[float] = 0.5


@dataclass(frozen=True)
class DescriptorLossWeights:
    """How much each of the three signals says in the total.

    The teacher supplies what sounds alike to people, the retuned views supply that a retuning
    changes nothing, and the labels supply what this listener called alike. Measured on a pilot,
    the retuning term buys the octave at a cost in agreement that the label term buys back, so its
    weight is the one worth sweeping.
    """

    distillation: float = DEFAULT_DISTILLATION_WEIGHT
    retuning: float = DEFAULT_RETUNING_WEIGHT
    labels: float = DEFAULT_LABEL_WEIGHT


def default_run_settings() -> RunSettings:
    """The run shape a descriptor is driven by when nothing else is asked: a small network, many short steps."""
    return RunSettings(
        epochs=DEFAULT_DESCRIPTOR_EPOCHS,
        batch_size=DEFAULT_DESCRIPTOR_BATCH_SIZE,
        learning_rate=DEFAULT_DESCRIPTOR_LEARNING_RATE,
    )


@dataclass(frozen=True)
class DescriptorTrainingSettings:
    """What a descriptor is taught with, beside how the run that teaches it is driven.

    A share of the labeled samples is held out from the label term so the run reports an agreement
    the descriptor was never taught, and each batch carries a fixed number of the rest so the term
    sees pairs to score. The validation gallery is the draw the retuning check ranks against.
    """

    run: RunSettings = field(default_factory=default_run_settings)
    weights: DescriptorLossWeights = field(default_factory=DescriptorLossWeights)
    width: int = DEFAULT_WIDTH
    label_holdout_share: float = DEFAULT_LABEL_HOLDOUT_SHARE
    labeled_per_batch: int = DEFAULT_LABELED_PER_BATCH
    validation_gallery: int = DEFAULT_VALIDATION_GALLERY

    def __post_init__(self) -> None:
        if not 0.0 < self.label_holdout_share < 1.0:
            raise ValueError(
                f"the held-out share of labels lies strictly between 0 and 1, got {self.label_holdout_share}"
            )
        if self.labeled_per_batch >= self.run.batch_size:
            raise TrainingRefused(
                f"a batch of {self.run.batch_size} cannot carry {self.labeled_per_batch} labeled samples and any others"
            )

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return self.run.as_parameters() | {
            "width": str(self.width),
            "distillation_weight": str(self.weights.distillation),
            "retuning_weight": str(self.weights.retuning),
            "label_weight": str(self.weights.labels),
            "label_holdout_share": str(self.label_holdout_share),
            "labeled_per_batch": str(self.labeled_per_batch),
            "validation_gallery": str(self.validation_gallery),
        }
