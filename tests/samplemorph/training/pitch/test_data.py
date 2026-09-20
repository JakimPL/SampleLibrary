from __future__ import annotations

from pathlib import Path

import numpy as np

from samplemorph.training.frame_cache import STORED_READING
from samplemorph.training.pitch.data import FrameBatchSampler, PitchCorpus, PitchDataModule
from samplemorph.training.pitch.settings import PitchTrainingSettings
from samplemorph.training.run_settings import RunSettings
from tests.samplemorph.training.pitch.conftest import ANALYSIS, write_frame_cache

BATCH_SIZE = 4
VALIDATION_COUNT = 4


def _corpus(library_root: Path) -> PitchCorpus:
    cache = write_frame_cache(library_root / "cache" / "frames" / "tiny")
    positions = np.arange(cache.sample_count)
    return PitchCorpus(
        cache=cache,
        library_root=library_root,
        training_positions=positions[VALIDATION_COUNT:],
        validation_positions=positions[:VALIDATION_COUNT],
    )


def test_every_batch_is_whole_and_reads_each_sample_at_one_of_its_frames_drawn_afresh_every_epoch() -> None:
    counts = np.full((32, 2), ANALYSIS.kept_frame_count, dtype=np.int16)
    sampler = FrameBatchSampler(np.arange(10, 31), counts=counts, batch_size=BATCH_SIZE, random_seed=0)

    first = list(sampler)
    sampler.sampler.set_epoch(1)
    second = list(sampler)

    assert len(first) == len(sampler) == 5
    assert all(len(batch) == BATCH_SIZE for batch in first)
    requests = [request for batch in first for request in batch]
    assert len({position for position, _ in requests}) == len(requests)
    assert {position for position, _ in requests} <= set(range(10, 31))
    assert {frame for _, frame in requests} <= set(range(ANALYSIS.kept_frame_count))
    assert first != second


def test_a_sample_that_kept_one_frame_is_always_read_at_it() -> None:
    counts = np.ones((8, 2), dtype=np.int16)
    sampler = FrameBatchSampler(np.arange(8), counts=counts, batch_size=BATCH_SIZE, random_seed=0)

    assert all(frame == 0 for batch in sampler for _, frame in batch)


def test_the_trainer_is_handed_one_frame_a_sample_to_learn_from_and_both_readings_to_be_judged_on(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path)
    settings = PitchTrainingSettings(run=RunSettings(batch_size=BATCH_SIZE, worker_count=0))

    data = PitchDataModule(corpus, settings=settings)

    frames = next(iter(data.train_dataloader()))
    stored, stored_count, retuned, retuned_count, offsets = next(iter(data.val_dataloader()))
    assert data.training_sample_count == corpus.cache.sample_count - VALIDATION_COUNT
    assert frames.shape == (BATCH_SIZE, ANALYSIS.band_count)
    assert stored.shape == retuned.shape == (BATCH_SIZE, ANALYSIS.kept_frame_count, ANALYSIS.band_count)
    assert np.array_equal(stored_count.numpy(), retuned_count.numpy())
    assert np.allclose(offsets.numpy(), corpus.cache.offsets[: len(offsets)])
    assert np.allclose(stored[0, 0].numpy(), corpus.cache.frames[0, STORED_READING, 0].astype(np.float32))
