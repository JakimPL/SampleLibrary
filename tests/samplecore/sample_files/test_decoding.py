from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import soundfile
from trackmod.binary.pcm.quantize import dequantize, quantize
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.sample_files.decoding import (
    UnsupportedSampleFileError,
    decode_sample_file,
    sample_file_frame_count,
)

RATE = 44100


def _waveform(frames: int, channels: int) -> np.ndarray:
    return np.linspace(-0.9, 0.9, frames * channels, dtype=np.float64).reshape(frames, channels)


@dataclass(frozen=True)
class DecodingCase:
    subtype: str
    channels: int
    depth: BitDepth


@pytest.mark.parametrize(
    "case",
    [
        DecodingCase(subtype="PCM_U8", channels=1, depth=BitDepth.EIGHT),
        DecodingCase(subtype="PCM_16", channels=1, depth=BitDepth.SIXTEEN),
        DecodingCase(subtype="PCM_16", channels=2, depth=BitDepth.SIXTEEN),
        DecodingCase(subtype="PCM_24", channels=2, depth=BitDepth.SIXTEEN),
        DecodingCase(subtype="FLOAT", channels=1, depth=BitDepth.SIXTEEN),
    ],
    ids=("unsigned 8-bit", "16-bit mono", "16-bit stereo", "24-bit", "floating point"),
)
def test_a_file_decodes_to_the_sample_its_quantized_frames_hash_to(tmp_path: Path, case: DecodingCase) -> None:
    path = tmp_path / "sound.wav"
    waveform = _waveform(64, case.channels)
    soundfile.write(path, waveform, RATE, subtype=case.subtype)

    decoded = decode_sample_file(path)

    written = soundfile.read(path, dtype="float64", always_2d=True)[0]
    expected = dequantize(quantize(written, case.depth), case.depth)
    channels = ChannelLayout(case.channels)
    assert decoded.sample_pcm.sample.depth is case.depth
    assert decoded.sample_pcm.sample.channels is channels
    assert np.array_equal(decoded.sample_pcm.pcm, expected)
    assert decoded.sample_pcm.sample.hash == compute_sample_hash(
        depth=case.depth, channels=channels, frames=64, pcm=expected
    )


def test_a_file_declares_the_rate_it_is_played_at(tmp_path: Path) -> None:
    path = tmp_path / "sound.flac"
    soundfile.write(path, _waveform(32, 1), 22050, subtype="PCM_16")

    assert decode_sample_file(path).rate == 22050


def test_a_file_holding_more_than_two_channels_is_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "surround.wav"
    soundfile.write(path, _waveform(16, 6), RATE, subtype="PCM_16")

    with pytest.raises(UnsupportedSampleFileError, match="6 channels"):
        decode_sample_file(path)


def test_a_file_holding_no_frames_is_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    soundfile.write(path, np.zeros((0, 1)), RATE, subtype="PCM_16")

    with pytest.raises(UnsupportedSampleFileError, match="no frames"):
        decode_sample_file(path)


def test_a_file_libsndfile_cannot_decode_raises_its_own_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"RIFF but nothing a decoder recognizes")

    with pytest.raises(soundfile.SoundFileError):
        decode_sample_file(path)


def test_a_missing_file_raises_an_operating_system_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        decode_sample_file(tmp_path / "gone.wav")


def test_the_frame_count_is_read_from_the_header(tmp_path: Path) -> None:
    path = tmp_path / "sound.aiff"
    soundfile.write(path, _waveform(128, 2), RATE, subtype="PCM_16")

    assert sample_file_frame_count(path) == 128
