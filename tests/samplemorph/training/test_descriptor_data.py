from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from samplemorph.training.descriptor_cache import GridSource, open_grid_cache
from samplemorph.training.descriptor_data import (
    NO_LABEL,
    STORED_VIEW,
    DescriptorCorpus,
    DescriptorDataModule,
    GridCacheSet,
    LabeledBatchSampler,
)
from samplemorph.training.descriptor_settings import DescriptorTrainingSettings
from samplemorph.training.run_settings import RunSettings
from tests.samplemorph.training.conftest import BAND_COUNT, CACHED_SAMPLE_COUNT, TIME_COLUMNS

SETTINGS = DescriptorTrainingSettings(
    run=RunSettings(batch_size=8, worker_count=0, random_seed=0), labeled_per_batch=2, validation_gallery=4
)


def test_a_cached_item_carries_a_stored_grid_beside_one_retuned_view(descriptor_corpus: DescriptorCorpus) -> None:
    dataset = GridCacheSet(
        GridSource.of(descriptor_corpus.cache),
        positions=np.arange(descriptor_corpus.sample_count),
        random_seed=0,
        fixed_view=None,
    )

    position, stored, retuned, stored_duration, retuned_duration = dataset[5]

    assert position == 5
    assert stored.shape == retuned.shape == (BAND_COUNT, TIME_COLUMNS)
    assert stored.dtype == retuned.dtype == np.float32
    assert stored_duration == retuned_duration


def test_a_fixed_view_reads_the_same_retuning_every_time(descriptor_corpus: DescriptorCorpus) -> None:
    dataset = GridCacheSet(
        GridSource.of(descriptor_corpus.cache),
        positions=np.arange(descriptor_corpus.sample_count),
        random_seed=0,
        fixed_view=STORED_VIEW,
    )

    first = dataset[3][2]
    second = dataset[3][2]

    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first, descriptor_corpus.cache.grids[3, 1].astype(np.float32))


def test_every_batch_carries_its_share_of_taught_labels() -> None:
    pool = np.arange(20)
    labeled = np.arange(20, 26)
    sampler = LabeledBatchSampler(pool=pool, labeled=labeled, batch_size=8, labeled_per_batch=3, random_seed=0)

    batches = list(sampler)

    assert len(sampler) == len(batches) == 4
    for batch in batches:
        assert len(batch) == 8
        assert sum(index in set(labeled.tolist()) for index in batch) == 3
        assert len(set(batch)) == 8


def test_the_held_out_labels_stay_out_of_training_and_inside_validation(descriptor_corpus: DescriptorCorpus) -> None:
    data = DescriptorDataModule(descriptor_corpus, settings=SETTINGS)

    training_positions = {index for batch in data.train_dataloader().batch_sampler for index in batch}
    validation_positions = {int(item[0]) for batch in data.val_dataloader() for item in zip(*batch)}

    held_out = set(descriptor_corpus.held_out_labeled_positions.tolist())
    assert held_out
    assert held_out.isdisjoint(training_positions)
    assert held_out <= validation_positions
    assert data.validation_sample_count == len(held_out) + 4
    assert data.training_sample_count == CACHED_SAMPLE_COUNT - len(held_out)


def test_a_corpus_names_its_taught_and_held_out_labels_apart(descriptor_corpus: DescriptorCorpus) -> None:
    taught = set(descriptor_corpus.taught_labeled_positions.tolist())
    held_out = set(descriptor_corpus.held_out_labeled_positions.tolist())

    assert taught.isdisjoint(held_out)
    assert taught | held_out == set(descriptor_corpus.labeled_positions.tolist())
    assert all(descriptor_corpus.label_position[position] != NO_LABEL for position in taught | held_out)


def test_a_missing_cache_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no grid cache"):
        open_grid_cache(tmp_path / "absent")
