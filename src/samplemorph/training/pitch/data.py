from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from samplemorph.training.epoch_draws import BatchesOfDraws
from samplemorph.training.frame_cache import RETUNED_READING, STORED_READING, FrameCache, FrameSource, MappedFrames
from samplemorph.training.loaders import CachedDataModule, build_batched_loader, build_loader
from samplemorph.training.pitch.settings import PitchTrainingSettings
from samplemorph.training.splits import CachedCorpus

FrameRequest = tuple[int, int]
# One held-out sample: its stored frames and how many it kept, its retuned frames and how many, and
# the retuning between the two.
HeldOutItem = tuple[NDArray[np.float32], int, NDArray[np.float32], int, float]
# The same, as the loader hands a batch of them to the trainer.
HeldOutBatch = tuple[Tensor, Tensor, Tensor, Tensor, Tensor]


# A frame cache split the way every trainer splits its cache.
PitchCorpus = CachedCorpus[FrameCache]


class StoredFrameSet(Dataset[NDArray[np.float32]]):
    """One frame of a sample's stored reading, the frame a request names; the file is mapped in whichever process reads it."""

    def __init__(self, source: FrameSource) -> None:
        self._frames = MappedFrames(source)

    def __getitem__(self, request: FrameRequest) -> NDArray[np.float32]:
        position, frame = request
        read: NDArray[np.float32] = self._frames.array()[position, STORED_READING, frame].astype(np.float32)
        return read


class HeldOutFrameSet(Dataset[HeldOutItem]):
    """Each held-out sample's two readings whole, with how many frames each kept and the retuning between them."""

    def __init__(self, source: FrameSource, *, positions: NDArray[np.intp]) -> None:
        self._frames = MappedFrames(source)
        self._source = source
        self._positions = positions

    def __len__(self) -> int:
        return len(self._positions)

    def __getitem__(self, index: int) -> HeldOutItem:
        position = int(self._positions[index])
        readings = self._frames.array()[position].astype(np.float32)
        counts = self._source.counts[position]
        return (
            readings[STORED_READING],
            int(counts[STORED_READING]),
            readings[RETUNED_READING],
            int(counts[RETUNED_READING]),
            float(self._source.offsets[position]),
        )


class FrameBatchSampler(BatchesOfDraws[FrameRequest]):
    """Whole batches of training samples, each read at one of its own stored frames drawn afresh every epoch.

    A sample is one item however long it sounds, so a held note and a hit count alike, and over the
    run every frame of every sample has its turn.
    """

    def __init__(
        self, positions: NDArray[np.intp], *, counts: NDArray[np.int16], batch_size: int, random_seed: int
    ) -> None:
        super().__init__(positions, batch_size=batch_size, random_seed=random_seed)
        self._counts = counts

    def drawn(self, positions: list[int], *, generator: np.random.Generator) -> list[FrameRequest]:
        kept = [max(int(self._counts[position, STORED_READING]), 1) for position in positions]
        return [(position, int(generator.integers(0, count))) for position, count in zip(positions, kept, strict=True)]


class PitchDataModule(CachedDataModule[FrameCache]):
    """Hands the trainer the cached frames: one frame of every training sample an epoch, and the held-out readings to be judged on."""

    def __init__(self, corpus: PitchCorpus, *, settings: PitchTrainingSettings) -> None:
        super().__init__(corpus, run=settings.run)
        self._source = FrameSource.of(corpus.cache)

    def train_dataloader(self) -> DataLoader[NDArray[np.float32]]:
        sampler = FrameBatchSampler(
            self._corpus.training_positions,
            counts=self._source.counts,
            batch_size=self._batch_size,
            random_seed=self._random_seed,
        )
        return build_batched_loader(
            StoredFrameSet(self._source), worker_count=self._worker_count, batch_sampler=sampler
        )

    def val_dataloader(self) -> DataLoader[HeldOutItem]:
        return build_loader(
            HeldOutFrameSet(self._source, positions=self._corpus.validation_positions),
            batch_size=self._batch_size,
            worker_count=self._worker_count,
            sampler=None,
            drop_last=False,
        )
