from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lightning.pytorch import LightningDataModule
from numpy.typing import NDArray
from sqlalchemy import Connection
from torch.utils.data import DataLoader, Dataset, Sampler

from samplecore.equivalence_classes import EquivalenceClass, classes_by_member_hash, compute_equivalence_classes
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplemorph.training.descriptor_cache import STORED_VIEW, GridCache, GridSource, MappedGrids
from samplemorph.training.epoch_draws import VIEW_STREAM, EpochPermutation, ViewRequest, epoch_generator
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.loaders import build_batched_loader, build_loader, require_full_batch
from samplemorph.training.refusals import TrainingDataShortfall


@dataclass(frozen=True)
class FeatureCorpus:
    """A grid cache split into the samples a feature model is taught on and the ones it is judged on."""

    cache: GridCache
    library_root: Path
    training_positions: NDArray[np.intp]
    validation_positions: NDArray[np.intp]

    @property
    def validation_hashes(self) -> tuple[str, ...]:
        return tuple(self.cache.hashes[int(position)] for position in self.validation_positions)


def load_feature_corpus(
    connection: Connection, *, cache: GridCache, library_root: Path, settings: FeatureTrainingSettings
) -> FeatureCorpus:
    """The cache split by the catalog's equivalence classes under the run's seed.

    Raises:
        TrainingDataShortfall: the split leaves nothing to train on or nothing to validate on.
    """
    classes = classes_by_member_hash(
        compute_equivalence_classes(PostgresSampleRelationRepository(connection).list_all())
    )
    held_out = held_out_by_class(
        cache.hashes, classes=classes, share=settings.validation_share, random_seed=settings.run.random_seed
    )
    if held_out.all() or not held_out.any():
        raise TrainingDataShortfall(
            f"holding out {settings.validation_share:.0%} of {cache.sample_count} cached samples by class leaves "
            "one side empty; cache more samples or change the validation share"
        )
    return FeatureCorpus(
        cache=cache,
        library_root=library_root,
        training_positions=np.flatnonzero(~held_out),
        validation_positions=np.flatnonzero(held_out),
    )


def held_out_by_class(
    hashes: tuple[str, ...], *, classes: Mapping[str, EquivalenceClass], share: float, random_seed: int
) -> NDArray[np.bool_]:
    """Which samples are held out: whole equivalence classes, drawn in the seed's order until `share` of the samples.

    A tracker module's copies of one sample share a class, so a copy of a validation sound never
    reaches training. A sample outside every class is a class of its own.
    """
    keys = np.asarray(
        [classes[sample_hash].class_hash if sample_hash in classes else sample_hash for sample_hash in hashes]
    )
    distinct, members = np.unique(keys, return_inverse=True)
    order = np.random.default_rng(random_seed).permutation(len(distinct))
    sizes = np.bincount(members, minlength=len(distinct))[order]
    chosen = order[: int(np.searchsorted(np.cumsum(sizes), share * len(hashes))) + 1]
    held_out: NDArray[np.bool_] = np.isin(members, chosen)
    return held_out


class ViewGridSet(Dataset[NDArray[np.float32]]):
    """Any cached sample's grid at the view a request names; the mapped file is opened in whichever process reads it."""

    def __init__(self, source: GridSource) -> None:
        self._grids = MappedGrids(source)

    def __getitem__(self, request: ViewRequest) -> NDArray[np.float32]:
        position, view = request
        grid: NDArray[np.float32] = self._grids.array()[position, view].astype(np.float32)
        return grid


class StoredGridSet(Dataset[NDArray[np.float32]]):
    """Chosen samples' stored grids in a fixed order, so every validation reads the same sounds."""

    def __init__(self, source: GridSource, *, positions: NDArray[np.intp]) -> None:
        self._grids = MappedGrids(source)
        self._positions = positions

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> NDArray[np.float32]:
        grid: NDArray[np.float32] = self._grids.array()[int(self._positions[index]), STORED_VIEW].astype(np.float32)
        return grid


class ViewBatchSampler(Sampler[list[ViewRequest]]):
    """Whole batches of training samples, each read at one of its views drawn afresh every epoch.

    The stored grid and every retuned view are equally likely, so the retuned views are ordinary
    training grids here. The order and the views are functions of the seed and the epoch the
    trainer hands to `sampler`.
    """

    def __init__(self, positions: NDArray[np.intp], *, batch_size: int, view_count: int, random_seed: int) -> None:
        super().__init__()
        self.sampler = EpochPermutation(positions, random_seed=random_seed)
        self._batch_size = batch_size
        self._view_count = view_count
        self._random_seed = random_seed

    def __len__(self) -> int:
        return len(self.sampler) // self._batch_size

    def __iter__(self) -> Iterator[list[ViewRequest]]:
        generator = epoch_generator(self._random_seed, stream=VIEW_STREAM, epoch=self.sampler.epoch)
        order = list(self.sampler)
        for start in range(0, len(self) * self._batch_size, self._batch_size):
            positions = order[start : start + self._batch_size]
            views = generator.integers(0, self._view_count, len(positions)).tolist()
            yield list(zip(positions, views, strict=True))


class FeatureDataModule(LightningDataModule):
    """Hands the trainer the cached grids: views of the training samples to learn from, the held-out stored grids to be judged on.

    Raises:
        TrainingDataShortfall: the training samples fill no batch.
    """

    def __init__(self, corpus: FeatureCorpus, *, settings: FeatureTrainingSettings) -> None:
        super().__init__()
        require_full_batch(len(corpus.training_positions), batch_size=settings.run.batch_size, flags="--batch")
        self._corpus = corpus
        self._batch_size = settings.run.batch_size
        self._worker_count = settings.run.worker_count
        self._random_seed = settings.run.random_seed

    @property
    def training_sample_count(self) -> int:
        return len(self._corpus.training_positions)

    def train_dataloader(self) -> DataLoader[NDArray[np.float32]]:
        sampler = ViewBatchSampler(
            self._corpus.training_positions,
            batch_size=self._batch_size,
            view_count=1 + self._corpus.cache.view_count,
            random_seed=self._random_seed,
        )
        return build_batched_loader(
            ViewGridSet(GridSource.of(self._corpus.cache)), worker_count=self._worker_count, batch_sampler=sampler
        )

    def val_dataloader(self) -> DataLoader[NDArray[np.float32]]:
        return build_loader(
            StoredGridSet(GridSource.of(self._corpus.cache), positions=self._corpus.validation_positions),
            batch_size=self._batch_size,
            worker_count=self._worker_count,
            sampler=None,
            drop_last=False,
        )
