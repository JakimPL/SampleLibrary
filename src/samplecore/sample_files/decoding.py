from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import soundfile
from trackmod.binary.pcm.quantize import dequantize, quantize
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM

SAMPLE_FILE_SUFFIXES: Final[frozenset[str]] = frozenset({".wav", ".aif", ".aiff", ".flac"})
EIGHT_BIT_SUBTYPES: Final[frozenset[str]] = frozenset({"PCM_U8", "PCM_S8"})
_SUPPORTED_CHANNEL_COUNTS: Final[frozenset[int]] = frozenset(layout.value for layout in ChannelLayout)


class UnsupportedSampleFileError(ValueError):
    """Raised when a file decodes to audio the catalog has no layout for."""


# What a file that opens but fails to decode raises: libsndfile's own refusal, or a layout the
# catalog cannot hold.
UNDECODABLE_SAMPLE_FILE_ERRORS: Final[tuple[type[Exception], ...]] = (
    soundfile.SoundFileError,
    UnsupportedSampleFileError,
)
# What reading a file in place can raise, from a file gone or unreadable to one that fails to decode.
UNREADABLE_SAMPLE_FILE_ERRORS: Final[tuple[type[Exception], ...]] = (OSError, *UNDECODABLE_SAMPLE_FILE_ERRORS)


@dataclass(frozen=True)
class DecodedSampleFile:
    """A sample file's audio in the catalog's own form, with the rate the file declares."""

    sample_pcm: SamplePCM
    rate: int


def decode_sample_file(path: Path) -> DecodedSampleFile:
    """Decode a plain audio file into the sample it holds, hashed the way every sample is.

    The suffixes read are lossless formats, whose decoding gives the same frames on every run, so a
    file keeps one hash for as long as its bytes stay the same. An 8-bit file stays at 8 bits and
    every deeper or floating-point encoding is quantized to 16, the deepest layout the catalog holds.
    The waveform returned is the quantized one, so reading a file gives exactly the frames its hash
    was computed from, the same frames a stored object of that hash would give.

    The file is opened here and handed to libsndfile as a stream, which separates a file that cannot
    be read from one that cannot be decoded.

    Raises:
        OSError: the file cannot be opened or read.
        soundfile.SoundFileError: libsndfile cannot decode the file.
        UnsupportedSampleFileError: the file holds no frames, or more channels than two.
    """
    with path.open("rb") as stream, soundfile.SoundFile(stream) as sound_file:
        if sound_file.channels not in _SUPPORTED_CHANNEL_COUNTS:
            raise UnsupportedSampleFileError(f"{path} holds {sound_file.channels} channels; mono or stereo is read")
        depth = BitDepth.EIGHT if sound_file.subtype in EIGHT_BIT_SUBTYPES else BitDepth.SIXTEEN
        rate = int(sound_file.samplerate)
        decoded = sound_file.read(dtype="float64", always_2d=True)

    frames, channel_count = decoded.shape
    if frames == 0:
        raise UnsupportedSampleFileError(f"{path} holds no frames")

    channels = ChannelLayout(channel_count)
    pcm = dequantize(quantize(decoded, depth), depth)
    sample = Sample(
        hash=compute_sample_hash(depth=depth, channels=channels, frames=frames, pcm=pcm),
        depth=depth,
        channels=channels,
        frames=frames,
    )
    return DecodedSampleFile(sample_pcm=SamplePCM(sample=sample, pcm=pcm), rate=rate)


def sample_file_frame_count(path: Path) -> int:
    """How many frames a sample file holds, read from its header alone.

    Raises:
        OSError: the file cannot be opened or read.
        soundfile.SoundFileError: libsndfile cannot decode the file.
    """
    with path.open("rb") as stream, soundfile.SoundFile(stream) as sound_file:
        return int(sound_file.frames)
