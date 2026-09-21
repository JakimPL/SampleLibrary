from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

FIRST_END_WEIGHT: Final[float] = 0.0
SECOND_END_WEIGHT: Final[float] = 1.0


@dataclass(frozen=True)
class TransportedSpectrogram:
    """A magnitude between two sounds, bins by frames, with the length in samples it sounds for."""

    magnitude: NDArray[np.float32]
    sample_count: int
