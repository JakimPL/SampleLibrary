from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from samplemorph.training.run_settings import RunSettings

DEFAULT_CROP_FRAMES: Final[int] = 128


@dataclass(frozen=True)
class AnalysisTrainingSettings:
    """What a model of the pipeline's magnitudes is taught with, beside how the run that teaches it is driven.

    Both families taught on derived examples, the phase model and the restorer, read a crop of
    analysis frames through a network of some width; `channels` carries no default because each
    family spends a different capacity.
    """

    channels: int
    run: RunSettings = field(default_factory=RunSettings)
    crop_frames: int = DEFAULT_CROP_FRAMES

    def as_parameters(self) -> dict[str, str]:
        """What this run was asked to do, in the form a tracker records."""
        return self.run.as_parameters() | {
            "crop_frames": str(self.crop_frames),
            "channels": str(self.channels),
        }
