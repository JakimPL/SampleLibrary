from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplemorph.geometry import SEMITONES_PER_OCTAVE

DEFAULT_HEAD_CHANNELS: Final[tuple[int, ...]] = (16, 32, 32)
DEFAULT_HEAD_KERNEL_SIZE: Final[int] = 7
# Twelve semitones either way at three bins to the semitone: the widest crop shift a training pair
# takes, and the room the output axis keeps beyond the bins the analysis reads.
DEFAULT_SHIFT_REACH_SEMITONES: Final[float] = 12.0
READOUT_REACH_SEMITONES: Final[float] = 1.0
# Where the classical readers are trusted from, which is what a head is compared against until
# its own readings say otherwise.
DEFAULT_HEAD_TRUST: Final[float] = 0.5


class PitchHeadShape(BaseModel):
    """The dimensions that fix a pitch head, recorded beside its weights.

    The head reads `band_count` constant-Q bins and answers with a distribution over `output_bins`
    of the same spacing, which reaches `shift_reach_bins` beyond the bins read at either end, so
    every pitch a crop can hold has a bin to land on. The body is one convolution per entry of
    `channels`, each `kernel_size` bins wide.
    """

    model_config = FROZEN

    band_count: int = Field(ge=1)
    bins_per_octave: int = Field(ge=1)
    shift_reach_bins: int = Field(ge=1)
    channels: tuple[int, ...] = DEFAULT_HEAD_CHANNELS
    kernel_size: int = Field(default=DEFAULT_HEAD_KERNEL_SIZE, ge=1)

    @property
    def bins_per_semitone(self) -> float:
        return self.bins_per_octave / SEMITONES_PER_OCTAVE

    @property
    def output_bins(self) -> int:
        return self.band_count + 2 * self.shift_reach_bins

    @property
    def readout_reach_bins(self) -> int:
        """How far either way of its peak a reading gathers the answer, a semitone at this spacing."""
        return max(int(round(READOUT_REACH_SEMITONES * self.bins_per_semitone)), 1)

    @property
    def toeplitz_kernel_size(self) -> int:
        """The length of the kernel that maps the bins read onto the bins answered, one weight per offset between them."""
        return self.band_count + self.output_bins - 1
