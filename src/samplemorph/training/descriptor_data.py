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
from samplemorph.training.descriptor_cache import GRIDS_FILE_NAME, STORED_VIEW, GridCache, GridSource
from samplemorph.training.descriptor_settings import DescriptorTrainingSettings
from samplemorph.training.loaders import build_loader

NO_LABEL: Final[int] = -1

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
        ValueError: a cached sample has no teacher vector, so the experiment does not cover the draw.
    """
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(teacher_experiment_id)
    by_hash = {vector.sample_hash: vector.vector for vector in vectors}
    missing = [sample_hash for sample_hash in cache.hashes if sample_hash not in by_hash]
    if missing:
        raise ValueError(
            f"experiment {teacher_experiment_id} holds no vector for {len(missing)} of the "
            f"{cache.sample_count} cached samples"
        )
    teacher = np.asarray([by_hash[sample_hash] for sample_hash in cache.hashes], dtype=np.float32)

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


class GridCacheSet(Dataset[DescriptorBatchItem]):
    """The cached grids of chosen samples, each read beside one of its retuned views.

    The mapped file is opened on first use in whichever process reads it.
    """

    def __init__(
        self, source: GridSource, *, positions: NDArray[np.intp], random_seed: int, fixed_view: int | None
    ) -> None:
        self._directory = source.directory
        self._positions = positions
        self._durations = source.durations
        self._view_count = source.view_count
        self._random_seed = random_seed
        self._fixed_view = fixed_view
        self._grids: NDArray[np.float16] | None = None

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> DescriptorBatchItem:
        position = int(self._positions[index])
        view = self._fixed_view if self._fixed_view is not None else self._drawn_view(index)
        grids = self._mapped_grids()
        return (
            position,
            grids[position, STORED_VIEW].astype(np.float32),
            grids[position, 1 + view].astype(np.float32),
            self._durations[position, STORED_VIEW],
            self._durations[position, 1 + view],
        )

    def _drawn_view(self, index: int) -> int:
        generator = np.random.default_rng(self._random_seed + index)
        return int(generator.integers(0, self._view_count))

    def _mapped_grids(self) -> NDArray[np.float16]:
        if self._grids is None:
            self._grids = np.load(self._directory / GRIDS_FILE_NAME, mmap_mode="r")
        return self._grids


class LabeledBatchSampler(Sampler[list[int]]):
    """Batches drawn from the whole pool, each carrying a fixed number of labeled samples.

    The label term scores pairs, so a batch that met a labeled sample by chance would rarely hold
    two. Every batch instead holds `labeled_per_batch` of the taught labeled samples beside its
    share of the pool, and each epoch walks the pool in a fresh order.
    """

    def __init__(
        self,
        *,
        pool: NDArray[np.intp],
        labeled: NDArray[np.intp],
        batch_size: int,
        labeled_per_batch: int,
        random_seed: int,
    ) -> None:
        super().__init__()
        self._pool = pool
        self._labeled = labeled
        self._labeled_per_batch = min(labeled_per_batch, len(labeled))
        self._pool_per_batch = batch_size - self._labeled_per_batch
        self._generator = np.random.default_rng(random_seed)

    def __len__(self) -> int:
        return len(self._pool) // self._pool_per_batch

    def __iter__(self) -> Iterator[list[int]]:
        order = self._generator.permutation(self._pool)
        for start in range(0, len(self) * self._pool_per_batch, self._pool_per_batch):
            batch = order[start : start + self._pool_per_batch].tolist()
            if self._labeled_per_batch:
                batch += self._generator.choice(self._labeled, self._labeled_per_batch, replace=False).tolist()
            yield batch


class DescriptorDataModule(LightningDataModule):
    """Hands the trainer the cached grids: a mixed batch to learn from, and a fixed set to be judged on.

    Training draws every cached sample but the held-out labeled ones, each batch carrying its share
    of taught labels. Validation reads the held-out labeled samples beside a gallery drawn once, at
    a fixed view, so the retuning check ranks each view against the same crowd every epoch.
    """

    def __init__(self, corpus: DescriptorCorpus, *, settings: DescriptorTrainingSettings) -> None:
        super().__init__()
        self._corpus = corpus
        self._batch_size = settings.run.batch_size
        self._labeled_per_batch = settings.labeled_per_batch
        self._worker_count = settings.run.worker_count
        self._random_seed = settings.run.random_seed
        held_out = corpus.held_out_labeled_positions
        everyone = np.arange(corpus.sample_count)
        candidates = np.setdiff1d(everyone, np.concatenate([held_out, corpus.labeled_positions]))
        generator = np.random.default_rng(settings.run.random_seed)
        gallery = generator.choice(candidates, size=min(settings.validation_gallery, len(candidates)), replace=False)
        self._validation_positions = np.sort(np.concatenate([held_out, gallery]))
        self._training_positions = np.setdiff1d(everyone, held_out)

    @property
    def training_sample_count(self) -> int:
        return len(self._training_positions)

    @property
    def validation_sample_count(self) -> int:
        return len(self._validation_positions)

    def train_dataloader(self) -> DataLoader[DescriptorBatchItem]:
        """Batches named by corpus position, so the sampler decides who is trained on and the set reads anyone."""
        dataset = self._dataset(np.arange(self._corpus.sample_count), fixed_view=None)
        sampler = LabeledBatchSampler(
            pool=np.setdiff1d(self._training_positions, self._corpus.taught_labeled_positions),
            labeled=self._corpus.taught_labeled_positions,
            batch_size=self._batch_size,
            labeled_per_batch=self._labeled_per_batch,
            random_seed=self._random_seed,
        )
        return self._loader(dataset, batch_sampler=sampler)

    def val_dataloader(self) -> DataLoader[DescriptorBatchItem]:
        return self._loader(self._dataset(self._validation_positions, fixed_view=STORED_VIEW), batch_sampler=None)

    def _dataset(self, positions: NDArray[np.intp], *, fixed_view: int | None) -> GridCacheSet:
        return GridCacheSet(
            GridSource.of(self._corpus.cache), positions=positions, random_seed=self._random_seed, fixed_view=fixed_view
        )

    def _loader(
        self, dataset: GridCacheSet, *, batch_sampler: LabeledBatchSampler | None
    ) -> DataLoader[DescriptorBatchItem]:
        return build_loader(
            dataset,
            batch_size=self._batch_size,
            worker_count=self._worker_count,
            shuffle=False,
            batch_sampler=batch_sampler,
        )
