from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from sampledescriptor.images import SoundImage


class Descriptor(Protocol):
    """Reads a canonical sound image as one fixed-length vector that says what the sound resembles.

    Distance between two of these vectors is what the cloud lays out and what the hand labels are
    scored against, so an implementation is judged by the evaluation harness rather than by its
    reconstruction, which it never attempts. The vector has the same length for every image, which
    is what lets a codec take it as conditioning.
    """

    @property
    def size(self) -> int: ...

    def describe(self, image: SoundImage) -> NDArray[np.float64]: ...
