from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class FeatureExtractor(Protocol):
    """Turns one Sample's waveform into a fixed-length descriptor vector for embedding.

    An implementation must return the same vector length for every call regardless of the input
    waveform's frame count, so that any two samples' vectors are directly comparable however long
    or short either recording is. The waveform it receives is already dequantized to float PCM
    (see ``samplecore.storage.audio_store.read``), so an implementation never has to account for
    the sample's original bit depth either -- both invariants are what let this project swap in a
    different extraction method later without touching the pipeline that calls it.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]: ...
