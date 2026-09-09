from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lightning.pytorch import LightningDataModule
from numpy.typing import NDArray
from torch.utils.data import DataLoader, Dataset

from samplemorph.descriptors.learned import LearnedDescriptor
from samplemorph.training.codec_settings import CodecTrainingSettings
from samplemorph.training.descriptor_cache import GRIDS_FILE_NAME, GridCache
from samplemorph.training.descriptor_data import STORED_VIEW, GridSource
from samplemorph.training.loaders import build_loader

# (position in the corpus, the stored grid at full resolution, its canonical duration)
CodecBatchItem = tuple[int, NDArray[np.float32], np.float32]


@dataclass(frozen=True)
class CodecCorpus:
    """A cache of full-resolution grids beside the descriptor the codec is conditioned on.

    The cache must hold the grid as the codec reads it, at the axis's own resolution; the
    descriptor reads its pooled form itself, so one cache serves both halves of every step.

    Raises:
        ValueError: the cache was pooled, so the grids are coarser than the codec reconstructs.
    """

    cache: GridCache
    library_root: Path
    descriptor: LearnedDescriptor
    descriptor_name: str

    def __post_init__(self) -> None:
        if self.cache.description.band_count != self.cache.description.geometry.grid_shape[0]:
            raise ValueError(
                f"a codec reads the grid at its own resolution, and the cache under {self.cache.directory} was pooled"
            )
        if self.cache.description.geometry != self.descriptor.description.geometry:
            raise ValueError("the cache and the descriptor describe different geometries")

    @property
    def sample_count(self) -> int:
        return self.cache.sample_count


class StoredGridSet(Dataset[CodecBatchItem]):
    """The stored grid of chosen samples, at full resolution, mapped on first use in each process."""

    def __init__(self, source: GridSource, *, positions: NDArray[np.intp]) -> None:
        self._directory = source.directory
        self._durations = source.durations
        self._positions = positions
        self._grids: NDArray[np.float16] | None = None

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> CodecBatchItem:
        position = int(self._positions[index])
        if self._grids is None:
            self._grids = np.load(self._directory / GRIDS_FILE_NAME, mmap_mode="r")
        return position, self._grids[position, STORED_VIEW].astype(np.float32), self._durations[position, STORED_VIEW]


class CodecDataModule(LightningDataModule):
    """Hands the trainer the cached grids, a held-back share drawn once for judging every epoch."""

    def __init__(self, corpus: CodecCorpus, *, settings: CodecTrainingSettings) -> None:
        super().__init__()
        self._corpus = corpus
        self._batch_size = settings.run.batch_size
        self._worker_count = settings.run.worker_count
        order = np.random.default_rng(settings.run.random_seed).permutation(corpus.sample_count)
        holdout = max(round(corpus.sample_count * settings.validation_share), 1)
        if corpus.sample_count <= holdout:
            raise ValueError(f"{corpus.sample_count} samples leave nothing to train on once {holdout} are held back")
        self._validation_positions = np.sort(order[:holdout])
        self._training_positions = np.sort(order[holdout:])

    @property
    def training_sample_count(self) -> int:
        return len(self._training_positions)

    @property
    def validation_sample_count(self) -> int:
        return len(self._validation_positions)

    def train_dataloader(self) -> DataLoader[CodecBatchItem]:
        return self._loader(self._training_positions, shuffle=True)

    def val_dataloader(self) -> DataLoader[CodecBatchItem]:
        return self._loader(self._validation_positions, shuffle=False)

    def _loader(self, positions: NDArray[np.intp], *, shuffle: bool) -> DataLoader[CodecBatchItem]:
        return build_loader(
            StoredGridSet(GridSource.of(self._corpus.cache), positions=positions),
            batch_size=self._batch_size,
            worker_count=self._worker_count,
            shuffle=shuffle,
        )
