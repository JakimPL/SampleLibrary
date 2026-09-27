from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class SampleFingerprint:
    """A sample's content read in brief, which candidate pairs of equivalent samples are searched through.

    `shape` and `rate` are unit vectors describing how the sound's spectrum spreads and how fast its
    cycles run, and `trimmed_frames` its length once trailing silence is trimmed. A silent sample
    holds no vectors: nothing in it is there to compare.
    """

    sample_hash: str
    trimmed_frames: int
    shape: NDArray[np.float32] | None
    rate: NDArray[np.float32] | None

    @property
    def silent(self) -> bool:
        return self.shape is None


@dataclass(frozen=True)
class StoredFingerprint:
    """A fingerprint as the catalog keeps it, with the comparison rule the sample was last compared under, if any."""

    fingerprint: SampleFingerprint
    compared_version: int | None
