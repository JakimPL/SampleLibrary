from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from lightning.pytorch import LightningDataModule
from numpy.typing import NDArray
from sqlalchemy import Connection
from torch.utils.data import DataLoader, Dataset, Sampler

from samplecore.labeling.labels import SampleLabel
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampledescriptor.descriptors.shape import DESCRIPTOR_SIZE
from sampledescriptor.training.descriptor.cache import (
    MINIMUM_RETUNED_VIEW_COUNT,
    STORED_VIEW,
    GridCache,
    GridSource,
    MappedGrids,
)
from sampledescriptor.training.descriptor.settings import DescriptorTrainingSettings
from sampledescriptor.training.epoch_draws import VIEW_STREAM, EpochPermutation, ViewRequest, epoch_generator
from sampledescriptor.training.loaders import build_batched_loader, build_loader, require_full_batch
from sampledescriptor.training.refusals import TrainingDataShortfall, TrainingRefused

NO_LABEL: Final[int] = -1
# Validation reads the first retuned view of every sample, the same one every epoch.
VALIDATION_VIEW: Final[int] = 0
GALLERY_SHARE_DIVISOR: Final[int] = 2

# (position in the corpus, stored grid, retuned grid, stored duration, retuned duration)
DescriptorBatchItem = tuple[int, NDArray[np.float32], NDArray[np.float32], np.float32, np.float32]


@dataclass(frozen=True)
class DescriptorCorpus:
    """A grid cache beside what its samples are taught against: the teacher's vectors and the labels.

    `teacher` lines up with the cache's samples row by row; `label_position` names, for each
    sample, its row in `labels` or `NO_LABEL`. Which labeled samples are taught and which are held
    out is drawn once, so every epoch reports on the same unseen labels.
    """

    cache: GridCache
    library_root: Path
    teacher_experiment_id: int
    teacher: NDArray[np.float32]
    labels: tuple[SampleLabel, ...]
    label_position: NDArray[np.int64]
    held_out_labels: NDArray[np.bool_]

    @property
    def sample_count(self) -> int:
        return self.cache.sample_count

    @property
    def labeled_positions(self) -> NDArray[np.intp]:
        return np.flatnonzero(self.label_position != NO_LABEL)

    @property
    def taught_labeled_positions(self) -> NDArray[np.intp]:
        """Samples whose label the run learns from."""
        return np.flatnonzero((self.label_position != NO_LABEL) & ~self.held_out_labels)

    @property
    def held_out_labeled_positions(self) -> NDArray[np.intp]:
        """Samples whose label the run is judged on and never shown."""
        return np.flatnonzero(self.held_out_labels)


def load_descriptor_corpus(
    connection: Connection,
    *,
    cache: GridCache,
    library_root: Path,
    teacher_experiment_id: int,
    settings: DescriptorTrainingSettings,
) -> DescriptorCorpus:
    """Join the cache's samples to their teacher vectors and their hand labels.

    The settings say what share of the labels is held out and under which seed.

    Raises:
        TrainingRefused: a cached sample has no teacher vector, so the experiment does not cover the
            draw, or the teacher's vectors are not the size a descriptor answers in.
    """
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(teacher_experiment_id)
    by_hash = {vector.sample_hash: vector.vector for vector in vectors}
    missing = [sample_hash for sample_hash in cache.hashes if sample_hash not in by_hash]
    if missing:
        raise TrainingRefused(
            f"experiment {teacher_experiment_id} holds no vector for {len(missing)} of the "
            f"{cache.sample_count} cached samples"
        )
    teacher = np.asarray([by_hash[sample_hash] for sample_hash in cache.hashes], dtype=np.float32)
    if teacher.shape[1] != DESCRIPTOR_SIZE:
        raise TrainingRefused(
            f"experiment {teacher_experiment_id} holds vectors of {teacher.shape[1]} numbers, and a descriptor is "
            f"distilled from a listening model's vectors of {DESCRIPTOR_SIZE}"
        )

    annotations = PostgresSampleAnnotationRepository(connection).annotations_by_hash(list(cache.hashes))
    labels: list[SampleLabel] = []
    label_position = np.full(cache.sample_count, NO_LABEL, dtype=np.int64)
    for position, sample_hash in enumerate(cache.hashes):
        annotation = annotations.get(sample_hash)
        if annotation is not None and annotation.label:
            label_position[position] = len(labels)
            labels.append(SampleLabel.parse(annotation.label))
    held_out = np.zeros(cache.sample_count, dtype=bool)
    labeled = np.flatnonzero(label_position != NO_LABEL)
    shuffled = np.random.default_rng(settings.run.random_seed).permutation(labeled)
    held_out[shuffled[: round(len(shuffled) * settings.label_holdout_share)]] = True
    return DescriptorCorpus(
        cache=cache,
        library_root=library_root,
        teacher_experiment_id=teacher_experiment_id,
        teacher=teacher,
        labels=tuple(labels),
        label_position=label_position,
        held_out_labels=held_out,
    )


class RetunedViewSet(Dataset[DescriptorBatchItem]):
    """Any cached sample's stored grid beside the retuned view a request names.

    The batch sampler draws which view pairs with each stored grid, every epoch afresh, so the
    views a cache holds are all read over a run. The mapped file is opened on first use in
    whichever process reads it.
    """

    def __init__(self, source: GridSource) -> None:
        self._grids = MappedGrids(source)
        self._durations = source.durations

    def __len__(self) -> int:
        return len(self._durations)

    def __getitem__(self, request: ViewRequest) -> DescriptorBatchItem:
        position, view = request
        return _paired(self._grids.array(), self._durations, position=position, view=view)


class FixedViewSet(Dataset[DescriptorBatchItem]):
    """Chosen samples' stored grids, each beside the same retuned view every epoch, so epochs compare."""

    def __init__(self, source: GridSource, *, positions: NDArray[np.intp], view: int) -> None:
        self._grids = MappedGrids(source)
        self._durations = source.durations
        self._positions = positions
        self._view = view

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> DescriptorBatchItem:
        return _paired(self._grids.array(), self._durations, position=int(self._positions[index]), view=self._view)


def _paired(
    grids: NDArray[np.float16], durations: NDArray[np.float32], *, position: int, view: int
) -> DescriptorBatchItem:
    return (
        position,
        grids[position, STORED_VIEW].astype(np.float32),
        grids[position, 1 + view].astype(np.float32),
        durations[position, STORED_VIEW],
        durations[position, 1 + view],
    )


@dataclass(frozen=True)
class BatchComposition:
    """What one training batch is made of: how many samples, how many of them taught labels, and how many views each offers."""

    batch_size: int
    labeled_per_batch: int
    view_count: int


class LabeledBatchSampler(Sampler[list[ViewRequest]]):
    """Batches drawn from the whole pool, each carrying a fixed number of labeled samples and a view for every sample.

    The label term scores pairs, so a batch that met a labeled sample by chance would rarely hold
    two. Every batch instead holds `labeled_per_batch` of the taught labeled samples beside its
    share of the pool. Each epoch walks the pool in a fresh order and draws fresh labeled samples
    and views, all from the seed and the epoch the trainer hands to `sampler`.
    """

    def __init__(
        self, *, pool: NDArray[np.intp], labeled: NDArray[np.intp], composition: BatchComposition, random_seed: int
    ) -> None:
        super().__init__()
        self.sampler = EpochPermutation(pool, random_seed=random_seed)
        self._labeled = labeled
        self._labeled_per_batch = min(composition.labeled_per_batch, len(labeled))
        self._pool_per_batch = composition.batch_size - self._labeled_per_batch
        self._view_count = composition.view_count
        self._random_seed = random_seed

    def __len__(self) -> int:
        return len(self.sampler) // self._pool_per_batch

    def __iter__(self) -> Iterator[list[ViewRequest]]:
        generator = epoch_generator(self._random_seed, stream=VIEW_STREAM, epoch=self.sampler.epoch)
        order = list(self.sampler)
        for start in range(0, len(self) * self._pool_per_batch, self._pool_per_batch):
            positions = order[start : start + self._pool_per_batch]
            if self._labeled_per_batch:
                positions += generator.choice(self._labeled, self._labeled_per_batch, replace=False).tolist()
            views = generator.integers(0, self._view_count, len(positions)).tolist()
            yield list(zip(positions, views, strict=True))


class DescriptorDataModule(LightningDataModule):
    """Hands the trainer the cached grids: a mixed batch to learn from, and a fixed set to be judged on.

    Training draws every cached sample but the validation ones, each batch carrying its share of
    taught labels. Validation reads the held-out labeled samples beside a gallery drawn once from
    the unlabeled samples, at a fixed view, so the retuning check ranks each view against the same
    crowd every epoch. The gallery takes at most half the unlabeled samples, which leaves a small
    library the other half to train on.

    Raises:
        TrainingDataShortfall: the cache holds no retuned views, nothing is left to validate on, or
            the unlabeled training samples fill no batch.
    """

    def __init__(self, corpus: DescriptorCorpus, *, settings: DescriptorTrainingSettings) -> None:
        super().__init__()
        if corpus.cache.view_count < MINIMUM_RETUNED_VIEW_COUNT:
            raise TrainingDataShortfall(
                f"the cache under {corpus.cache.directory} holds no retuned views, which teach a descriptor that "
                "a retuning changes nothing; build it with --views 1 or more"
            )
        self._corpus = corpus
        self._batch_size = settings.run.batch_size
        self._worker_count = settings.run.worker_count
        self._random_seed = settings.run.random_seed
        held_out = corpus.held_out_labeled_positions
        everyone = np.arange(corpus.sample_count)
        candidates = np.setdiff1d(everyone, np.concatenate([held_out, corpus.labeled_positions]))
        generator = np.random.default_rng(settings.run.random_seed)
        gallery_size = min(settings.validation_gallery, len(candidates) // GALLERY_SHARE_DIVISOR)
        gallery = generator.choice(candidates, size=gallery_size, replace=False)
        self._validation_positions = np.sort(np.concatenate([held_out, gallery]))
        if self._validation_positions.size == 0:
            raise TrainingDataShortfall(
                "every cached sample is a taught label, which leaves nothing to validate on; cache more samples "
                "or raise --label-holdout"
            )
        self._training_positions = np.setdiff1d(everyone, self._validation_positions)
        self._labeled_per_batch = min(settings.labeled_per_batch, len(corpus.taught_labeled_positions))
        self._pool = np.setdiff1d(self._training_positions, corpus.taught_labeled_positions)
        require_full_batch(
            len(self._pool) + self._labeled_per_batch,
            batch_size=self._batch_size,
            flags="--batch and --labeled-per-batch",
        )

    @property
    def training_sample_count(self) -> int:
        return len(self._training_positions)

    @property
    def validation_sample_count(self) -> int:
        return len(self._validation_positions)

    def train_dataloader(self) -> DataLoader[DescriptorBatchItem]:
        """Batches of (position, view) requests, so the sampler decides who is trained on and which view each reads."""
        sampler = LabeledBatchSampler(
            pool=self._pool,
            labeled=self._corpus.taught_labeled_positions,
            composition=BatchComposition(
                batch_size=self._batch_size,
                labeled_per_batch=self._labeled_per_batch,
                view_count=self._corpus.cache.view_count,
            ),
            random_seed=self._random_seed,
        )
        return build_batched_loader(
            RetunedViewSet(GridSource.of(self._corpus.cache)), worker_count=self._worker_count, batch_sampler=sampler
        )

    def val_dataloader(self) -> DataLoader[DescriptorBatchItem]:
        return build_loader(
            FixedViewSet(GridSource.of(self._corpus.cache), positions=self._validation_positions, view=VALIDATION_VIEW),
            batch_size=self._batch_size,
            worker_count=self._worker_count,
            sampler=None,
            drop_last=False,
        )
