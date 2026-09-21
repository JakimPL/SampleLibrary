from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from sampledescriptor.geometry import GridGeometry


class Conditioners(BaseModel):
    """What a sound image was normalized by, stated relative to the stored waveform.

    The corpus assigns a sample's playback rate per occurrence rather than per content hash, so
    every quantity here is measured against the frames as they sit in the content store and no
    absolute rate is ever asserted. `translation_semitones` is how far an anchoring rule moved the
    picture, and reads zero when the geometry names no rule. Under a rule, reading the same
    waveform at a rate `alpha` times higher raises the translation by ``12 * log2(alpha)`` and
    lowers `log_duration` by ``log2(alpha)``, which leaves ``translation_semitones + 12 *
    log_duration`` untouched -- the invariant that says the pair describes one reading of one
    waveform.
    """

    model_config = FROZEN

    translation_semitones: float
    log_duration: float
    log_gain: float


@dataclass(frozen=True)
class SoundImage:
    """A sample's canonical fixed-size picture, together with what it was normalized by.

    `grid` holds normalized log magnitude in ``[0, 1]``, on a frequency axis by duration-fraction
    grid whose shape is the same for every sample however long or loud it was. By default every
    band holds the frequency the analysis measured, so a kick and a pad sit where they sound. Under an anchoring rule the band the rule picks is moved to the
    geometry's reference band instead, so two readings of one waveform at different rates produce
    the same grid and differing conditioners.
    """

    grid: NDArray[np.float64]
    conditioners: Conditioners
    geometry: GridGeometry

    def __post_init__(self) -> None:
        if self.grid.shape != self.geometry.grid_shape:
            raise ValueError(
                f"sound image grid is {self.grid.shape}, and its geometry asks for {self.geometry.grid_shape}"
            )
        if not np.all(np.isfinite(self.grid)):
            raise ValueError("sound image grid carries values that are not finite")
        if self.grid.min() < 0.0 or self.grid.max() > 1.0:
            raise ValueError(
                f"sound image grid spans [{self.grid.min()}, {self.grid.max()}], and must lie within [0, 1]"
            )

    @property
    def band_count(self) -> int:
        return int(self.grid.shape[0])

    @property
    def time_columns(self) -> int:
        return int(self.grid.shape[1])
