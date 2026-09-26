from __future__ import annotations

from collections.abc import Sequence
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

    `extract_many` describes a batch, one vector per waveform in order. An extractor reading one
    sample at a time takes the default by naming this protocol as its base; a model reading a batch
    in one pass answers it faster.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]: ...

    def extract_many(self, waveforms: Sequence[NDArray[np.float64]]) -> list[NDArray[np.float64]]:
        return [self.extract(waveform) for waveform in waveforms]
