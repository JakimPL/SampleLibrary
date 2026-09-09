from __future__ import annotations

from dataclasses import dataclass, field

from samplemorph.training.phase_dataset import DEFAULT_CROP_FRAMES
from samplemorph.training.phase_losses import LossWeights
from samplemorph.training.run_settings import RunSettings
from samplemorph.vocoders.phase_model import DEFAULT_CHANNELS


@dataclass(frozen=True)
class PhaseTrainingSettings:
    """What a phase model is taught with, beside how the run that teaches it is driven."""

    run: RunSettings = field(default_factory=RunSettings)
    crop_frames: int = DEFAULT_CROP_FRAMES
    channels: int = DEFAULT_CHANNELS
    weights: LossWeights = field(default_factory=LossWeights)

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return self.run.as_parameters() | {
            "crop_frames": str(self.crop_frames),
            "channels": str(self.channels),
            "gradient_weight": str(self.weights.gradient),
            "spectral_weight": str(self.weights.spectral),
        }
