from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from samplemorph.images import AnalysisSpectrogram


class Vocoder(Protocol):
    """Turns a magnitude spectrogram back into frames a person can listen to.

    The spectrogram carries the geometry that gave its rows meaning, so one implementation serves
    every frequency axis this project analyzes on and a caller hands over one self-describing
    object rather than an array plus a convention held elsewhere.

    Keeping this apart from the canonicalizer is what makes "how much does the phase estimate cost"
    answerable: hold the representation fixed, swap the vocoder, and the difference belongs to the
    vocoder alone.
    """

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]: ...
