from __future__ import annotations

import wave
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from trackmod.binary.pcm.quantise import dequantise, quantise
from trackmod.core.samples.depth import BitDepth

from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM

NOMINAL_WAV_RATE: Final[int] = 44100
OBJECTS_DIRECTORY_NAME: Final[str] = "objects"
_UNSIGNED_EIGHT_BIT_OFFSET: Final[int] = 128


def object_path(library_root: Path, sample_hash: str) -> Path:
    """Where a Sample's audio lives under the content-addressable store, sharded by hash prefix."""
    return library_root / OBJECTS_DIRECTORY_NAME / sample_hash[:2] / f"{sample_hash}.wav"


def write(library_root: Path, sample_pcm: SamplePCM) -> Path:
    """Write a Sample's waveform to the content-addressable store as a plain PCM WAV file.

    Writing is skipped when the object already exists: content-addressed storage means a second
    write for the same hash could only ever repeat the same bytes.

    The stored bytes are quantised with TrackMod's own signed convention, exactly matching what
    the sample's hash was computed from. Only 8-bit PCM is offset before writing, to the WAV
    format's own unsigned storage convention for that depth -- 16-bit stays signed, matching both
    TrackMod and WAV directly -- so the quantised values the hash is derived from are only ever
    re-expressed in whichever byte convention the container demands, never altered. The header's
    sample rate is a fixed nominal value, not any occurrence's real playback rate: Sample excludes
    rate by design, and the real rate(s) for this content live in SampleProperties rows instead.
    """
    sample = sample_pcm.sample
    path = object_path(library_root, sample.hash)
    if path.is_file():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    quantised = quantise(sample_pcm.pcm, sample.depth)
    # pylint mis-infers wave.open's mode-dependent overload as Wave_read even for "wb"; mypy resolves it correctly.
    # pylint: disable=no-member
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(sample.channels.value)
        wav_file.setsampwidth(sample.depth.bytes_per_frame)
        wav_file.setframerate(NOMINAL_WAV_RATE)
        wav_file.writeframes(_encode_frames(quantised, sample.depth))
    # pylint: enable=no-member

    return path


def read(library_root: Path, sample: Sample) -> SamplePCM:
    """Read a Sample's waveform back from the content-addressable store."""
    path = object_path(library_root, sample.hash)
    with wave.open(str(path), "rb") as wav_file:
        frame_bytes = wav_file.readframes(wav_file.getnframes())

    quantised = _decode_frames(frame_bytes, sample.depth, sample.channels.value)
    return SamplePCM(sample=sample, pcm=dequantise(quantised, sample.depth))


def _encode_frames(quantised: NDArray[np.int64], depth: BitDepth) -> bytes:
    if depth is BitDepth.EIGHT:
        return (quantised + _UNSIGNED_EIGHT_BIT_OFFSET).astype(np.uint8).tobytes()

    return quantised.astype("<i2").tobytes()


def _decode_frames(frame_bytes: bytes, depth: BitDepth, channels: int) -> NDArray[np.int64]:
    if depth is BitDepth.EIGHT:
        flat = np.frombuffer(frame_bytes, dtype=np.uint8).astype(np.int64) - _UNSIGNED_EIGHT_BIT_OFFSET
    else:
        flat = np.frombuffer(frame_bytes, dtype="<i2").astype(np.int64)

    return flat.reshape(-1, channels)
