from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Generic, TypeVar

import numpy as np
from lightning.pytorch import LightningDataModule
from torch.utils.data import DataLoader

from samplecore.models.sample import Sample
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.training.derived_examples import DerivedExampleSet, ExampleFamily
from samplemorph.training.epoch_draws import EpochCropSampler, FixedCropSampler
from samplemorph.training.loaders import build_loader, require_full_batch
from samplemorph.training.refusals import TrainingDataShortfall
from samplemorph.training.run_settings import RunSettings

DEFAULT_VALIDATION_SHARE: Final[float] = 0.05

Example = TypeVar("Example")
Item = TypeVar("Item")


@dataclass(frozen=True)
class AnalysisCorpus:
    """The material a model of the pipeline's magnitudes is taught from: which samples, read from where, on which axis.

    The axis travels with the samples because the magnitudes a model learns from are produced by it,
    so a model is only ever valid for the canonicalizer it was taught on.
    """

    samples: tuple[Sample, ...]
    audio: SampleAudio
    canonicalizer: Canonicalizer
    canonicalizer_name: str


class AnalysisDataModule(LightningDataModule, Generic[Example, Item]):
    """Hands the trainer the two parts of a corpus, on a transport a long run survives.

    Which samples are trained on and which are held back is drawn once, so every epoch is judged on
    the same unseen material and two runs of one seed see the same division. Training samples are
    walked in a fresh order each epoch, each with a fresh crop; validation samples keep their crop
    every epoch. Each worker derives examples from the audio itself, in the roughly 730 MB its own
    imports and working arrays need, on the transport `build_loader` describes. The family says
    which examples a worker derives, so one module serves every model taught on the pipeline's
    magnitudes.

    Raises:
        TrainingDataShortfall: the corpus is too small to hold a share back and still fill a batch.
    """

    def __init__(self, corpus: AnalysisCorpus, *, family: ExampleFamily[Example, Item], run: RunSettings) -> None:
        super().__init__()
        self._corpus = corpus
        self._family = family
        self._run = run
        self._training_samples, self._validation_samples = split_held_back(corpus.samples, random_seed=run.random_seed)
        require_full_batch(len(self._training_samples), batch_size=run.batch_size, flags="--batch")

    @property
    def training_sample_count(self) -> int:
        return len(self._training_samples)

    @property
    def validation_sample_count(self) -> int:
        return len(self._validation_samples)

    def train_dataloader(self) -> DataLoader[Item]:
        return build_loader(
            self._examples(self._training_samples),
            batch_size=self._run.batch_size,
            worker_count=self._run.worker_count,
            sampler=EpochCropSampler(len(self._training_samples), random_seed=self._run.random_seed),
            drop_last=True,
        )

    def val_dataloader(self) -> DataLoader[Item]:
        return build_loader(
            self._examples(self._validation_samples),
            batch_size=self._run.batch_size,
            worker_count=self._run.worker_count,
            sampler=FixedCropSampler(len(self._validation_samples), random_seed=self._run.random_seed),
            drop_last=False,
        )

    def _examples(self, samples: tuple[Sample, ...]) -> DerivedExampleSet[Example, Item]:
        return DerivedExampleSet(
            samples,
            audio=self._corpus.audio,
            canonicalizer=self._corpus.canonicalizer,
            family=self._family,
        )


def split_held_back(samples: tuple[Sample, ...], *, random_seed: int) -> tuple[tuple[Sample, ...], tuple[Sample, ...]]:
    """Draw a held-back part once, so every epoch is judged on the same unseen material.

    Raises:
        TrainingDataShortfall: the body is too small to hold any of it back.
    """
    holdout = max(round(len(samples) * DEFAULT_VALIDATION_SHARE), 1)
    if len(samples) <= holdout:
        raise TrainingDataShortfall(f"{len(samples)} samples leave nothing to train on once {holdout} are held back")

    order = np.random.default_rng(random_seed).permutation(len(samples))
    return (
        tuple(samples[position] for position in order[holdout:]),
        tuple(samples[position] for position in order[:holdout]),
    )
