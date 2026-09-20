from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from torch.utils.data import DataLoader, Dataset

from samplemorph.training.descriptor_cache import STORED_VIEW, GridCache, GridSource, MappedGrids
from samplemorph.training.epoch_draws import BatchesOfDraws, ViewRequest
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.loaders import CachedDataModule, build_batched_loader, build_loader
from samplemorph.training.splits import CachedCorpus

# A grid cache split the way every trainer splits its cache.
FeatureCorpus = CachedCorpus[GridCache]


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


class ViewBatchSampler(BatchesOfDraws[ViewRequest]):
    """Whole batches of training samples, each read at one of its views drawn afresh every epoch.

    The stored grid and every retuned view are equally likely, so the retuned views are ordinary
    training grids here.
    """

    def __init__(self, positions: NDArray[np.intp], *, batch_size: int, view_count: int, random_seed: int) -> None:
        super().__init__(positions, batch_size=batch_size, random_seed=random_seed)
        self._view_count = view_count

    def drawn(self, positions: list[int], *, generator: np.random.Generator) -> list[ViewRequest]:
        views = generator.integers(0, self._view_count, len(positions)).tolist()
        return list(zip(positions, views, strict=True))


class FeatureDataModule(CachedDataModule[GridCache]):
    """Hands the trainer the cached grids: views of the training samples to learn from, the held-out stored grids to be judged on."""

    def __init__(self, corpus: FeatureCorpus, *, settings: FeatureTrainingSettings) -> None:
        super().__init__(corpus, run=settings.run)

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
