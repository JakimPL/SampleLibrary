from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store


def _sample_pcm(depth: BitDepth, channels: ChannelLayout, pcm: np.ndarray) -> SamplePCM:
    frames = pcm.shape[0]
    sample_hash = compute_sample_hash(depth=depth, channels=channels, frames=frames, pcm=pcm)
    sample = Sample(hash=sample_hash, depth=depth, channels=channels, frames=frames)
    return SamplePCM(sample=sample, pcm=pcm)


def test_object_path_shards_by_the_first_two_hash_characters(tmp_path: Path) -> None:
    path = audio_store.object_path(tmp_path, "ab" + "c" * 62)

    assert path == tmp_path / "objects" / "ab" / f"{'ab' + 'c' * 62}.wav"


def test_a_mono_sixteen_bit_sample_round_trips_exactly(tmp_path: Path) -> None:
    pcm = np.array([-1.0, -0.5, 0.0, 0.5, 0.999], dtype=np.float64).reshape(-1, 1)
    sample_pcm = _sample_pcm(BitDepth.SIXTEEN, ChannelLayout.MONO, pcm)

    audio_store.write(tmp_path, sample_pcm)
    read_back = audio_store.read(tmp_path, sample_pcm.sample)

    assert np.array_equal(read_back.pcm, sample_pcm.pcm) or np.allclose(
        read_back.pcm, sample_pcm.pcm, atol=1.0 / BitDepth.SIXTEEN.scale
    )


def test_a_mono_eight_bit_sample_round_trips_exactly(tmp_path: Path) -> None:
    pcm = np.array([-1.0, -0.5, 0.0, 0.5, 0.999], dtype=np.float64).reshape(-1, 1)
    sample_pcm = _sample_pcm(BitDepth.EIGHT, ChannelLayout.MONO, pcm)

    audio_store.write(tmp_path, sample_pcm)
    read_back = audio_store.read(tmp_path, sample_pcm.sample)

    assert np.allclose(read_back.pcm, sample_pcm.pcm, atol=1.0 / BitDepth.EIGHT.scale)


def test_a_stereo_sample_round_trips_with_channels_preserved(tmp_path: Path) -> None:
    pcm = np.array([[-1.0, 1.0], [0.0, 0.0], [0.5, -0.5]], dtype=np.float64)
    sample_pcm = _sample_pcm(BitDepth.SIXTEEN, ChannelLayout.STEREO, pcm)

    audio_store.write(tmp_path, sample_pcm)
    read_back = audio_store.read(tmp_path, sample_pcm.sample)

    assert read_back.pcm.shape == (3, 2)


def test_reading_back_the_stored_bytes_reproduces_the_original_hash(tmp_path: Path) -> None:
    pcm = np.array([-1.0, -0.5, 0.0, 0.5, 0.999], dtype=np.float64).reshape(-1, 1)
    sample_pcm = _sample_pcm(BitDepth.EIGHT, ChannelLayout.MONO, pcm)

    audio_store.write(tmp_path, sample_pcm)
    read_back = audio_store.read(tmp_path, sample_pcm.sample)
    rehashed = compute_sample_hash(
        depth=read_back.sample.depth,
        channels=read_back.sample.channels,
        frames=read_back.sample.frames,
        pcm=read_back.pcm,
    )

    assert rehashed == sample_pcm.sample.hash


def test_writing_twice_is_idempotent_and_does_not_raise(tmp_path: Path) -> None:
    pcm = np.zeros((4, 1), dtype=np.float64)
    sample_pcm = _sample_pcm(BitDepth.SIXTEEN, ChannelLayout.MONO, pcm)

    first_path = audio_store.write(tmp_path, sample_pcm)
    second_path = audio_store.write(tmp_path, sample_pcm)

    assert first_path == second_path


def test_reading_a_sample_that_was_never_written_raises(tmp_path: Path) -> None:
    sample = Sample(hash="d" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)

    with pytest.raises(FileNotFoundError):
        audio_store.read(tmp_path, sample)
