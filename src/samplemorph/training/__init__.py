from __future__ import annotations

from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from samplemorph.codecs import SampleCodec


class CodecTrainer(Protocol):
    """Fits a codec to a body of sound images laid out one grid per row, producing one ready to encode and decode.

    Training is kept in its own package so that decoding reaches for none of the machinery fitting
    needs: the served side of this project depends on a `SampleCodec` and never on a trainer, and
    the import contracts hold that apart.
    """

    def fit(self, grids: NDArray[np.float32]) -> SampleCodec: ...


# Every worker process a trainer or a cache builder starts is a fresh interpreter, which is what
# keeps a worker's memory its own rather than a copy of a process holding the GPU.
WORKER_START_METHOD: Final[str] = "spawn"
