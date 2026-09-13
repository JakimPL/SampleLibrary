from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import Geometry
from samplemorph.images import AnalysisSpectrogram, SoundImage


class Canonicalizer(Protocol):
    """Turns a stored waveform into the fixed-size sound image every codec trades in, and back.

    An implementation returns the same grid shape for every waveform however long or loud it was,
    so any two samples' images are directly comparable and a codec sees one geometry throughout.
    The frequency axis is logarithmic, which turns a change of playback rate into a translation
    along it; the translation is measured, moved out of the grid, and carried as a conditioner, so
    the grid describes timbre and the conditioners describe the reading it was heard at.

    `restore` returns a magnitude spectrogram rather than audio, which leaves phase estimation to a
    `Vocoder` and keeps the two questions -- what the representation loses, and what the phase
    estimate loses -- answerable one at a time.
    """

    @property
    def geometry(self) -> Geometry: ...

    def canonicalize(self, waveform: NDArray[np.float64]) -> SoundImage: ...

    def restore(self, image: SoundImage) -> AnalysisSpectrogram: ...
