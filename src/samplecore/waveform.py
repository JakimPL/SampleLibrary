from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN

DEFAULT_WAVEFORM_BUCKET_COUNT: Final[int] = 200


class WaveformPeak(BaseModel):
    """One bucket's amplitude envelope in a compact waveform preview."""

    model_config = FROZEN

    minimum: float
    maximum: float


def compute_waveform_peaks(pcm: NDArray[np.float64], *, bucket_count: int) -> tuple[WaveformPeak, ...]:
    """Downsample a waveform's amplitude envelope into `bucket_count` min/max buckets.

    Multi-channel audio is mixed to mono first, matching the same `mean(axis=1)` pattern used
    for equivalence fingerprinting and cloud feature extraction, since a preview shows overall
    amplitude rather than per-channel detail. `bucket_count` is clamped to the frame count, so a
    sample shorter than the requested resolution still produces one bucket per frame.
    """
    mono = pcm.mean(axis=1)
    effective_bucket_count = min(bucket_count, mono.shape[0])
    buckets = np.array_split(mono, effective_bucket_count)
    return tuple(WaveformPeak(minimum=float(bucket.min()), maximum=float(bucket.max())) for bucket in buckets)
