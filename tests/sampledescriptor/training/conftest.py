from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from lightning.pytorch import LightningModule, Trainer
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch.utils.data import DataLoader, Dataset

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.ranking import agreement_matrix
from sampledescriptor.descriptors.shape import DescriptorShape
from sampledescriptor.training.descriptor.cache import (
    DESCRIPTION_FILE_NAME,
    DURATIONS_FILE_NAME,
    GRIDS_FILE_NAME,
    HASHES_FILE_NAME,
    GridCache,
    GridCacheDescription,
    open_grid_cache,
)
from sampledescriptor.training.descriptor.data import NO_LABEL, DescriptorCorpus
from sampledescriptor.training.descriptor.module import DescriptorTrainingModule, TeachingMaterial
from sampledescriptor.training.descriptor.settings import DescriptorLossWeights
from sampledescriptor.training.metrics import DESCRIPTOR_TRAINING_LOSS, DESCRIPTOR_VALIDATION_LOSS
from sampledescriptor.training.optimizers import scheduled_over_the_run
from samplemorph.geometry import log_frequency_geometry

CROP_COUNT = 4
LEARNING_RATE = 1e-3


@pytest.fixture(name="fast_trainer")
def fixture_fast_trainer() -> Trainer:
    """One batch of each kind on the processor, writing nothing, so a test says only what it asks."""
    return Trainer(fast_dev_run=True, accelerator="cpu", logger=False, enable_checkpointing=False)


TINY_FEATURE_COUNT = 6
TinyBatch = tuple[torch.Tensor, torch.Tensor]


class TinySet(Dataset[TinyBatch]):
    """Feature rows beside the targets a linear map reads off them."""

    def __init__(self, count: int = CROP_COUNT) -> None:
        self._count = count

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> TinyBatch:
        generator = torch.Generator().manual_seed(index)
        features = torch.rand(TINY_FEATURE_COUNT, generator=generator)
        return features, features.sum().reshape(1)


# pylint: disable=arguments-differ
class TinyModule(LightningModule):
    """A linear regression logging the descriptor's loss names, which stands for any module a run trains."""

    def __init__(self, *, learning_rate: float = LEARNING_RATE) -> None:
        super().__init__()
        self.layer = torch.nn.Linear(TINY_FEATURE_COUNT, 1)
        self._learning_rate = learning_rate

    def training_step(self, batch: TinyBatch, _batch_index: int) -> torch.Tensor:
        loss = self._loss(batch)
        self.log(DESCRIPTOR_TRAINING_LOSS, loss, on_step=True, on_epoch=True, prog_bar=True)
        return loss

    def validation_step(self, batch: TinyBatch, _batch_index: int) -> torch.Tensor:
        loss = self._loss(batch)
        self.log(DESCRIPTOR_VALIDATION_LOSS, loss, on_epoch=True, prog_bar=True)
        return loss

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        return scheduled_over_the_run(self, self.parameters(), learning_rate=self._learning_rate)

    def _loss(self, batch: TinyBatch) -> torch.Tensor:
        features, targets = batch
        return torch.nn.functional.mse_loss(self.layer(features), targets)


@pytest.fixture(name="tiny_module")
def fixture_tiny_module() -> TinyModule:
    torch.manual_seed(0)
    return TinyModule()


@pytest.fixture(name="tiny_loader")
def fixture_tiny_loader() -> DataLoader[TinyBatch]:
    return DataLoader(TinySet(), batch_size=2)


BAND_COUNT = 16
TIME_COLUMNS = 8
TEACHER_SIZE = 12
CACHED_SAMPLE_COUNT = 24
VIEW_COUNT = 2
LABELS = ("KICK: SOFT", "KICK: HARD", "SNARE", "SNARE, LO-FI", "BASS: SYNTH", "LEAD, SYNTH")


def write_grid_cache(
    directory: Path, *, sample_count: int = CACHED_SAMPLE_COUNT, view_count: int = VIEW_COUNT
) -> GridCache:
    """A small cache whose grids say which of six sounds a sample is, plus a little noise per view."""
    generator = np.random.default_rng(0)
    grids = np.zeros((sample_count, 1 + view_count, BAND_COUNT, TIME_COLUMNS), dtype=np.float16)
    durations = np.zeros((sample_count, 1 + view_count), dtype=np.float32)
    for position in range(sample_count):
        kind = position % len(LABELS)
        pattern = np.zeros((BAND_COUNT, TIME_COLUMNS))
        pattern[kind * 2 : kind * 2 + 2] = 1.0
        # What tells one sample from another of its kind stays the same across its views.
        own = generator.normal(0.0, 0.2, pattern.shape)
        for view in range(1 + view_count):
            grids[position, view] = np.clip(pattern + own + generator.normal(0.0, 0.02, pattern.shape), 0.0, 1.0)
            durations[position, view] = float(kind) / len(LABELS)
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / GRIDS_FILE_NAME, grids)
    np.save(directory / DURATIONS_FILE_NAME, durations)
    hashes = [format(position + 1, "064x") for position in range(sample_count)]
    (directory / HASHES_FILE_NAME).write_text("\n".join(hashes), encoding="utf-8")
    description = GridCacheDescription(
        canonicalizer="log_frequency",
        geometry=log_frequency_geometry(),
        bands_per_semitone=1,
        band_count=BAND_COUNT,
        time_columns=TIME_COLUMNS,
        sample_count=sample_count,
        view_count=view_count,
        view_range_semitones=12.0,
        random_seed=0,
    )
    (directory / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(), encoding="utf-8")
    return open_grid_cache(directory)


def synthetic_corpus(directory: Path, *, labeled_share: int = 2, view_count: int = VIEW_COUNT) -> DescriptorCorpus:
    """The cache beside a teacher that already separates the six sounds, and a label on every `labeled_share`-th sample."""
    cache = write_grid_cache(directory, view_count=view_count)
    teacher = np.zeros((cache.sample_count, TEACHER_SIZE), dtype=np.float32)
    labels: list[SampleLabel] = []
    label_position = np.full(cache.sample_count, NO_LABEL, dtype=np.int64)
    for position in range(cache.sample_count):
        kind = position % len(LABELS)
        teacher[position, kind] = 1.0
        if position % labeled_share == 0:
            label_position[position] = len(labels)
            labels.append(SampleLabel.parse(LABELS[kind]))
    held_out = np.zeros(cache.sample_count, dtype=bool)
    labeled = np.flatnonzero(label_position != NO_LABEL)
    held_out[labeled[::3]] = True
    return DescriptorCorpus(
        cache=cache,
        library_root=directory.parent.parent.parent,
        teacher_experiment_id=1,
        teacher=teacher,
        labels=tuple(labels),
        label_position=label_position,
        held_out_labels=held_out,
    )


@pytest.fixture(name="descriptor_corpus")
def fixture_descriptor_corpus(tmp_path: Path) -> DescriptorCorpus:
    return synthetic_corpus(tmp_path / "cache" / "grids" / "tiny")


@pytest.fixture(name="descriptor_module")
def fixture_descriptor_module(descriptor_corpus: DescriptorCorpus) -> DescriptorTrainingModule:
    torch.manual_seed(0)
    return DescriptorTrainingModule(
        DescriptorShape(
            band_count=BAND_COUNT, time_columns=TIME_COLUMNS, width=4, stage_count=2, embedding_size=TEACHER_SIZE
        ),
        learning_rate=LEARNING_RATE,
        weights=DescriptorLossWeights(),
        material=TeachingMaterial(
            teacher=torch.from_numpy(descriptor_corpus.teacher),
            label_position=torch.from_numpy(descriptor_corpus.label_position),
            held_out=torch.from_numpy(descriptor_corpus.held_out_labels),
            agreements=torch.from_numpy(agreement_matrix(descriptor_corpus.labels)).float(),
        ),
    )
