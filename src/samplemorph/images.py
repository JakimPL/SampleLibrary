from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplemorph.geometry import Geometry


class Conditioners(BaseModel):
    """What a sound image was normalized by, stated relative to the stored waveform.

    The corpus assigns a sample's playback rate per occurrence rather than per content hash, so
    every quantity here is measured against the frames as they sit in the content store and no
    absolute rate is ever asserted. Reading the same waveform at a rate `alpha` times higher raises
    `translation_semitones` by ``12 * log2(alpha)`` and lowers `log_duration` by ``log2(alpha)``,
    which leaves ``translation_semitones + 12 * log_duration`` untouched -- the invariant that says
    the pair describes one reading of one waveform.
    """

    model_config = FROZEN

    translation_semitones: float
    log_duration: float
    log_gain: float


@dataclass(frozen=True)
class SoundImage:
    """A sample's canonical fixed-size picture, together with what it was normalized by.

    `grid` holds normalized log magnitude in ``[0, 1]``, on a frequency axis by duration-fraction
    grid whose shape is the same for every sample however long or loud it was. The dominant partial
    is moved to the geometry's reference band, so two readings of one waveform at different rates
    produce the same grid and differing conditioners. That separation is what lets a linear codec
    interpolate two samples at different pitches into a single sound rather than a chord of both.
    """

    grid: NDArray[np.float64]
    conditioners: Conditioners
    geometry: Geometry

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


@dataclass(frozen=True)
class AnalysisSpectrogram:
    """A linear magnitude spectrogram on a named axis, ready for a vocoder to make audible.

    `frame_count` travels alongside because a magnitude spectrogram states how many analysis frames
    it holds while the waveform length it came from is a separate fact, and a restored image is
    expected to sound for the duration its conditioners recorded.
    """

    magnitude: NDArray[np.float64]
    geometry: Geometry
    frame_count: int

    def __post_init__(self) -> None:
        if self.magnitude.ndim != 2:
            raise ValueError(f"analysis spectrogram must be 2-D (bands, frames), got shape {self.magnitude.shape}")
        if self.magnitude.shape[0] != self.geometry.band_count:
            raise ValueError(
                f"analysis spectrogram carries {self.magnitude.shape[0]} bands, "
                f"and its geometry asks for {self.geometry.band_count}"
            )
        if self.frame_count < 1:
            raise ValueError(f"analysis spectrogram must sound for at least one frame, got {self.frame_count}")


@dataclass(frozen=True)
class SampleLatent:
    """A sound image's grid reduced to a fixed-length code, beside the conditioners it kept.

    The conditioners travel untouched: they describe the reference frame the grid was normalized
    into, and a codec spends its capacity on the grid alone. Interpolating the two separately is
    what lets a morph move timbre while pitch stays put, or the reverse.
    """

    values: NDArray[np.float64]
    conditioners: Conditioners
    geometry: Geometry

    def __post_init__(self) -> None:
        if self.values.ndim != 1:
            raise ValueError(f"a sample latent must be 1-D, got shape {self.values.shape}")
        if not np.all(np.isfinite(self.values)):
            raise ValueError("a sample latent carries values that are not finite")

    @property
    def latent_size(self) -> int:
        return int(self.values.shape[0])
