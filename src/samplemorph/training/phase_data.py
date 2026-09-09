from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from lightning.pytorch import LightningDataModule
from torch.utils.data import DataLoader

from samplecore.models.sample import Sample
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.training.loaders import build_loader
from samplemorph.training.phase_dataset import PhaseBatchItem, PhaseTrainingSet

DEFAULT_VALIDATION_SHARE: Final[float] = 0.05


@dataclass(frozen=True)
class PhaseCorpus:
    """The material a phase model is taught from: which samples, read from where, on which axis.

    The axis travels with the samples because the magnitudes a model learns from are produced by it,
    so a model is only ever valid for the canonicalizer it was taught on.
    """

    samples: tuple[Sample, ...]
    library_root: Path
    canonicalizer: Canonicalizer
    canonicalizer_name: str


class PhaseDataModule(LightningDataModule):
    """Hands the trainer the two parts of a corpus, on a transport a long run survives.

    Which samples are trained on and which are held back is drawn once, so every epoch is judged on
    the same unseen material and two runs of one seed see the same division. Each worker derives
    examples from the audio itself, in the roughly 730 MB its own imports and working arrays need,
    on the transport `build_loader` describes.
    """

    def __init__(
        self,
        corpus: PhaseCorpus,
        *,
        batch_size: int,
        crop_frames: int,
        worker_count: int,
        random_seed: int,
    ) -> None:
        super().__init__()
        self._corpus = corpus
        self._batch_size = batch_size
        self._crop_frames = crop_frames
        self._worker_count = worker_count
        self._random_seed = random_seed
        self._training_samples, self._validation_samples = _split(corpus.samples, random_seed=random_seed)

    @property
    def training_sample_count(self) -> int:
        return len(self._training_samples)

    @property
    def validation_sample_count(self) -> int:
        return len(self._validation_samples)

    def train_dataloader(self) -> DataLoader[PhaseBatchItem]:
        return self._loader(self._training_samples, shuffle=True)

    def val_dataloader(self) -> DataLoader[PhaseBatchItem]:
        return self._loader(self._validation_samples, shuffle=False)

    def _loader(self, samples: tuple[Sample, ...], *, shuffle: bool) -> DataLoader[PhaseBatchItem]:
        dataset = PhaseTrainingSet(
            samples,
            library_root=self._corpus.library_root,
            canonicalizer=self._corpus.canonicalizer,
            crop_frames=self._crop_frames,
            random_seed=self._random_seed,
        )
        return build_loader(dataset, batch_size=self._batch_size, worker_count=self._worker_count, shuffle=shuffle)


def _split(samples: tuple[Sample, ...], *, random_seed: int) -> tuple[tuple[Sample, ...], tuple[Sample, ...]]:
    """Draw a held-back part once, so every epoch is judged on the same unseen material.

    Raises:
        ValueError: the body is too small to hold any of it back.
    """
    holdout = max(round(len(samples) * DEFAULT_VALIDATION_SHARE), 1)
    if len(samples) <= holdout:
        raise ValueError(f"{len(samples)} samples leave nothing to train on once {holdout} are held back")

    order = np.random.default_rng(random_seed).permutation(len(samples))
    return (
        tuple(samples[position] for position in order[holdout:]),
        tuple(samples[position] for position in order[:holdout]),
    )
