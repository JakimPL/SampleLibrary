from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.coordinates.frames import frame_analysis
from samplemorph.tones import HarmonicTone, harmonic_tone
from samplemorph.training.frame_cache import (
    COUNTS_FILE_NAME,
    RETUNED_READING,
    STORED_READING,
    FrameCacheRecipe,
    build_frame_cache,
    open_frame_cache,
)

RATE_HZ = 44100.0
RANGE_SEMITONES = 7.0
SAMPLE_COUNT = 3


def _samples(library_root: Path) -> tuple[Sample, ...]:
    samples = []
    for index in range(SAMPLE_COUNT):
        pcm = harmonic_tone(
            HarmonicTone(fundamental_hz=110.0 * (index + 1), resonance_hz=1500.0, seconds=0.5), rate_hz=RATE_HZ
        )
        sample = Sample(
            hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=pcm.shape[0]
        )
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
        samples.append(sample)
    return tuple(samples)


def _recipe() -> FrameCacheRecipe:
    return FrameCacheRecipe(analysis=frame_analysis(), retuning_range_semitones=RANGE_SEMITONES, random_seed=0)


def _profile_shift_bins(stored: np.ndarray, retuned: np.ndarray) -> int:
    first, second = stored.astype(np.float32).mean(axis=0), retuned.astype(np.float32).mean(axis=0)
    reach = int(RANGE_SEMITONES * 3) + 3
    lags = range(-reach, reach + 1)
    scores = [
        float(np.dot(first[max(0, -lag) : first.size - max(0, lag)], second[max(0, lag) : second.size - max(0, -lag)]))
        for lag in lags
    ]
    return lags[int(np.argmax(scores))]


def test_every_sample_is_cached_as_stored_and_at_its_saved_retuning(tmp_path: Path) -> None:
    samples = _samples(tmp_path)

    cache = build_frame_cache(
        tmp_path / "cache" / "frames" / "pitch",
        samples=samples,
        audio=SampleAudio.of_files(tmp_path, ()),
        recipe=_recipe(),
        worker_count=0,
    )

    reopened = open_frame_cache(cache.directory)
    assert reopened.hashes == tuple(sample.hash for sample in samples)
    analysis = cache.description.analysis
    assert reopened.frames.shape == (SAMPLE_COUNT, 2, analysis.kept_frame_count, analysis.band_count)
    assert np.all(reopened.counts > 0)
    assert np.all(np.abs(reopened.offsets) <= RANGE_SEMITONES)
    for position in range(SAMPLE_COUNT):
        counts = reopened.counts[position]
        shift = _profile_shift_bins(
            reopened.frames[position, STORED_READING, : counts[STORED_READING]],
            reopened.frames[position, RETUNED_READING, : counts[RETUNED_READING]],
        )
        assert abs(shift - 3.0 * float(reopened.offsets[position])) <= 1.0


def test_a_cache_whose_files_disagree_is_refused(tmp_path: Path) -> None:
    cache = build_frame_cache(
        tmp_path / "cache" / "frames" / "pitch",
        samples=_samples(tmp_path),
        audio=SampleAudio.of_files(tmp_path, ()),
        recipe=_recipe(),
        worker_count=0,
    )
    np.save(cache.directory / COUNTS_FILE_NAME, np.zeros((1, 2), dtype=np.int16))

    with pytest.raises(ValueError, match="incomplete"):
        open_frame_cache(cache.directory)


def test_an_empty_draw_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        build_frame_cache(
            tmp_path / "pitch", samples=(), audio=SampleAudio.of_files(tmp_path, ()), recipe=_recipe(), worker_count=0
        )
