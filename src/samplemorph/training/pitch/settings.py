from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplemorph.coordinates.pitch_head.shape import DEFAULT_HEAD_TRUST, DEFAULT_SHIFT_REACH_SEMITONES
from samplemorph.training.run_settings import RunSettings
from samplemorph.training.splits import DEFAULT_VALIDATION_SHARE

DEFAULT_PITCH_EPOCHS: Final[int] = 20
DEFAULT_PITCH_BATCH_SIZE: Final[int] = 256
DEFAULT_PITCH_LEARNING_RATE: Final[float] = 1e-3
DEFAULT_EQUIVARIANCE_WEIGHT: Final[float] = 1.0
DEFAULT_SHIFT_WEIGHT: Final[float] = 1.0
DEFAULT_INVARIANCE_WEIGHT: Final[float] = 1.0


class AugmentationSettings(BaseModel):
    """What one view of a frame may have done to it, all of which leave its pitch where it is.

    A smooth envelope of `envelope_orders` cosines, up to `envelope_db` either way, stands for every
    body a series can sound through. The shelves cut up to `cut_depth_db` away below and above a
    drawn bin over `cut_ramp_bins`, which is a fundamental lost to a small speaker at one end and an
    8,363 Hz playback at the other. The floor lifts the quiet bins to up to `noise_floor` of the
    frame's own range, which is a sound heard through noise.
    """

    model_config = FROZEN

    envelope_orders: int = Field(default=4, ge=1)
    envelope_db: float = Field(default=15.0, ge=0.0)
    cut_depth_db: float = Field(default=40.0, ge=0.0)
    cut_ramp_bins: int = Field(default=12, ge=1)
    noise_floor: float = Field(default=0.4, ge=0.0, le=1.0)

    def as_parameters(self) -> dict[str, str]:
        return {f"augmentation_{name}": str(value) for name, value in self.model_dump().items()}


def default_run_settings() -> RunSettings:
    """The run shape a pitch head is driven by when nothing else is asked."""
    return RunSettings(
        epochs=DEFAULT_PITCH_EPOCHS,
        batch_size=DEFAULT_PITCH_BATCH_SIZE,
        learning_rate=DEFAULT_PITCH_LEARNING_RATE,
    )


@dataclass(frozen=True)
class PitchTrainingSettings:
    """What a pitch head is taught with, beside how the run that teaches it is driven.

    Two crops of one frame, each shifted by up to `shift_reach_semitones` and augmented on its own,
    carry the three terms: `equivariance_weight` prices how far the shift between their answers
    departs from the shift between the crops, `shift_weight` prices the answers against each other
    bin by bin, and `invariance_weight` holds two augmentations of one crop to one answer.
    `validation_share` of the cached samples is held out, whole equivalence classes at a time, and
    `trusted_reliability` is the reading a route glides by once the head is stored.

    Raises:
        ValueError: a weight is negative, or a share lies outside its bounds.
    """

    run: RunSettings = field(default_factory=default_run_settings)
    shift_reach_semitones: float = DEFAULT_SHIFT_REACH_SEMITONES
    equivariance_weight: float = DEFAULT_EQUIVARIANCE_WEIGHT
    shift_weight: float = DEFAULT_SHIFT_WEIGHT
    invariance_weight: float = DEFAULT_INVARIANCE_WEIGHT
    augmentation: AugmentationSettings = field(default_factory=AugmentationSettings)
    validation_share: float = DEFAULT_VALIDATION_SHARE
    trusted_reliability: float = DEFAULT_HEAD_TRUST

    def __post_init__(self) -> None:
        weights = (self.equivariance_weight, self.shift_weight, self.invariance_weight)
        if any(weight < 0.0 for weight in weights):
            raise ValueError(f"every loss weight must be at least 0, got {weights}")
        if self.shift_reach_semitones <= 0.0:
            raise ValueError(f"the crops shift by a positive number of semitones, got {self.shift_reach_semitones}")
        if not 0.0 < self.validation_share < 1.0:
            raise ValueError(f"the validation share lies strictly between 0 and 1, got {self.validation_share}")
        if not 0.0 <= self.trusted_reliability <= 1.0:
            raise ValueError(f"the trusted reliability lies between 0 and 1, got {self.trusted_reliability}")

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return (
            self.run.as_parameters()
            | {
                "shift_reach_semitones": str(self.shift_reach_semitones),
                "equivariance_weight": str(self.equivariance_weight),
                "shift_weight": str(self.shift_weight),
                "invariance_weight": str(self.invariance_weight),
                "validation_share": str(self.validation_share),
                "trusted_reliability": str(self.trusted_reliability),
            }
            | self.augmentation.as_parameters()
        )
