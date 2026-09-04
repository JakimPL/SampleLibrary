from __future__ import annotations

import hashlib
from typing import Final

import numpy as np
from numpy.typing import NDArray
from trackmod.binary.pcm.quantise import quantise
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout

HASH_DOMAIN: Final[str] = "sample-library:sample:v1"


def compute_sample_hash(*, depth: BitDepth, channels: ChannelLayout, frames: int, pcm: NDArray[np.float64]) -> str:
    """The content-addressed identity of a waveform at a given bit depth and channel layout.

    The hash domain-separates on depth, channel count, and frame count before hashing the
    quantised payload, git-blob style, so two different (depth, channels, frames) combinations
    can never collide on identical short or silent payload bytes. Quantisation reuses TrackMod's
    own signed convention at both depths, so two extractions of the same source audio always agree
    on the hash regardless of which code path decoded it.
    """
    payload = quantise(pcm, depth).astype(f"<i{depth.bytes_per_frame}").tobytes()
    header = f"{HASH_DOMAIN}:{depth.value}:{channels.value}:{frames}\0".encode("ascii")
    return hashlib.sha256(header + payload).hexdigest()
