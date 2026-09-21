from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sampledescriptor.training.descriptor.cache import GridSource, open_grid_cache
from sampledescriptor.training.descriptor.data import (
    NO_LABEL,
    BatchComposition,
    DescriptorCorpus,
    DescriptorDataModule,
    FixedViewSet,
    LabeledBatchSampler,
    RetunedViewSet,
)
from sampledescriptor.training.descriptor.settings import DescriptorTrainingSettings
from sampledescriptor.training.refusals import TrainingDataShortfall
from sampledescriptor.training.run.settings import RunSettings
from tests.sampledescriptor.training.conftest import (
    BAND_COUNT,
    CACHED_SAMPLE_COUNT,
    TIME_COLUMNS,
    VIEW_COUNT,
    synthetic_corpus,
)

SETTINGS = DescriptorTrainingSettings(
    run=RunSettings(batch_size=8, worker_count=0, random_seed=0), labeled_per_batch=2, validation_gallery=4
)


def test_a_requested_item_carries_a_stored_grid_beside_the_view_it_names(descriptor_corpus: DescriptorCorpus) -> None:
    dataset = RetunedViewSet(GridSource.of(descriptor_corpus.cache))

    position, stored, retuned, stored_duration, retuned_duration = dataset[(5, 1)]

    assert position == 5
    assert stored.shape == retuned.shape == (BAND_COUNT, TIME_COLUMNS)
    assert stored.dtype == retuned.dtype == np.float32
    np.testing.assert_array_equal(retuned, descriptor_corpus.cache.grids[5, 2].astype(np.float32))
    assert stored_duration == retuned_duration


def test_a_fixed_view_reads_the_same_retuning_every_time(descriptor_corpus: DescriptorCorpus) -> None:
    dataset = FixedViewSet(
        GridSource.of(descriptor_corpus.cache), positions=np.arange(descriptor_corpus.sample_count), view=0
    )

    first = dataset[3][2]
    second = dataset[3][2]

    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first, descriptor_corpus.cache.grids[3, 1].astype(np.float32))


def _sampler(*, view_count: int = VIEW_COUNT, random_seed: int = 0) -> LabeledBatchSampler:
    return LabeledBatchSampler(
        pool=np.arange(20),
        labeled=np.arange(20, 26),
        composition=BatchComposition(batch_size=8, labeled_per_batch=3, view_count=view_count),
        random_seed=random_seed,
    )


def _epoch(sampler: LabeledBatchSampler, epoch: int) -> list[list[tuple[int, int]]]:
    sampler.sampler.set_epoch(epoch)
    return list(sampler)


def test_every_batch_carries_its_share_of_taught_labels() -> None:
    sampler = _sampler()

    batches = _epoch(sampler, 0)

    assert len(sampler) == len(batches) == 4
    for batch in batches:
        positions = [position for position, _ in batch]
        assert len(positions) == 8
        assert sum(position >= 20 for position in positions) == 3
        assert len(set(positions)) == 8


def test_each_epoch_draws_its_own_order_views_and_labels_and_replays_them_under_one_seed() -> None:
    """A retuned view drawn once per sample would leave every other stored view unread for the whole run."""
    first_epoch = _epoch(_sampler(), 0)

    assert _epoch(_sampler(), 1) != first_epoch
    assert _epoch(_sampler(), 0) == first_epoch
    assert {view for batch in first_epoch for _, view in batch} == set(range(VIEW_COUNT))


def test_the_trainer_reaches_the_epoch_through_the_loader(descriptor_corpus: DescriptorCorpus) -> None:
    loader = DescriptorDataModule(descriptor_corpus, settings=SETTINGS).train_dataloader()

    assert isinstance(loader.batch_sampler, LabeledBatchSampler)
    loader.batch_sampler.sampler.set_epoch(3)
    assert loader.batch_sampler.sampler.epoch == 3


def test_the_validation_samples_stay_out_of_training(descriptor_corpus: DescriptorCorpus) -> None:
    data = DescriptorDataModule(descriptor_corpus, settings=SETTINGS)
    loader = data.train_dataloader()
    assert isinstance(loader.batch_sampler, LabeledBatchSampler)

    training_positions = {position for batch in loader.batch_sampler for position, _ in batch}
    validation_positions = {int(item[0]) for batch in data.val_dataloader() for item in zip(*batch)}

    held_out = set(descriptor_corpus.held_out_labeled_positions.tolist())
    assert held_out
    assert held_out <= validation_positions
    assert training_positions.isdisjoint(validation_positions)
    assert data.validation_sample_count == len(held_out) + SETTINGS.validation_gallery
    assert data.training_sample_count == CACHED_SAMPLE_COUNT - data.validation_sample_count


def test_a_cache_without_retuned_views_is_refused_for_a_descriptor(tmp_path: Path) -> None:
    corpus = synthetic_corpus(tmp_path / "cache" / "grids" / "flat", view_count=0)

    with pytest.raises(TrainingDataShortfall, match="--views 1"):
        DescriptorDataModule(corpus, settings=SETTINGS)


def test_a_library_too_small_for_one_batch_names_the_flags_that_shrink_it(descriptor_corpus: DescriptorCorpus) -> None:
    settings = DescriptorTrainingSettings(
        run=RunSettings(batch_size=64, worker_count=0, random_seed=0), labeled_per_batch=2, validation_gallery=4
    )

    with pytest.raises(TrainingDataShortfall, match="--batch and --labeled-per-batch"):
        DescriptorDataModule(descriptor_corpus, settings=settings)


def test_a_corpus_names_its_taught_and_held_out_labels_apart(descriptor_corpus: DescriptorCorpus) -> None:
    taught = set(descriptor_corpus.taught_labeled_positions.tolist())
    held_out = set(descriptor_corpus.held_out_labeled_positions.tolist())

    assert taught.isdisjoint(held_out)
    assert taught | held_out == set(descriptor_corpus.labeled_positions.tolist())
    assert all(descriptor_corpus.label_position[position] != NO_LABEL for position in taught | held_out)


def test_a_missing_cache_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no grid cache"):
        open_grid_cache(tmp_path / "absent")
