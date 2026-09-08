from __future__ import annotations

import hashlib
from typing import Final

import numpy as np
from numpy.typing import NDArray
from trackmod.binary.pcm.quantize import quantize
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout

HASH_DOMAIN: Final[str] = "sample-library:sample:v1"
EQUIVALENCE_CLASS_HASH_DOMAIN: Final[str] = "sample-library:equivalence-class:v1"


def compute_sample_hash(*, depth: BitDepth, channels: ChannelLayout, frames: int, pcm: NDArray[np.float64]) -> str:
    """The content-addressed identity of a waveform at a given bit depth and channel layout.

    The hash domain-separates on depth, channel count, and frame count before hashing the
    quantized payload, git-blob style, so two different (depth, channels, frames) combinations
    can never collide on identical short or silent payload bytes. Quantization reuses TrackMod's
    own signed convention at both depths, so two extractions of the same source audio always agree
    on the hash regardless of which code path decoded it.
    """
    payload = quantize(pcm, depth).astype(f"<i{depth.bytes_per_frame}").tobytes()
    header = f"{HASH_DOMAIN}:{depth.value}:{channels.value}:{frames}\0".encode("ascii")
    return hashlib.sha256(header + payload).hexdigest()


def compute_module_hash(data: bytes) -> str:
    """The content-addressed identity of a tracker module file, from its raw bytes.

    A module file's bytes are their own unambiguous identity, with no shape or depth ambiguity to
    guard against the way a sample's decoded waveform has, so this hashes the raw bytes directly.
    """
    return hashlib.sha256(data).hexdigest()


def compute_equivalence_class_hash(member_hashes: tuple[str, ...]) -> str:
    """The content-addressed identity of an equivalence class, from its members' own hashes.

    Sorting the member hashes before hashing means the same group of samples always resolves to
    the same class hash, regardless of which order the relations that discovered it were found or
    traversed in.
    """
    header = f"{EQUIVALENCE_CLASS_HASH_DOMAIN}\0".encode("ascii")
    payload = "\0".join(sorted(member_hashes)).encode("ascii")
    return hashlib.sha256(header + payload).hexdigest()
