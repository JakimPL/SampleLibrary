from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader, Dataset

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.ranking import agreement_matrix
from samplemorph.descriptors.grid_descriptor import DescriptorShape
from samplemorph.geometry import log_frequency_geometry
from samplemorph.training.descriptor_cache import (
    DESCRIPTION_FILE_NAME,
    DURATIONS_FILE_NAME,
    GRIDS_FILE_NAME,
    HASHES_FILE_NAME,
    GridCache,
    GridCacheDescription,
    open_grid_cache,
)
from samplemorph.training.descriptor_data import NO_LABEL, DescriptorCorpus
from samplemorph.training.descriptor_losses import DescriptorLossWeights
from samplemorph.training.descriptor_module import DescriptorTrainingModule, TeachingMaterial
from samplemorph.training.phase_dataset import PhaseBatchItem
from samplemorph.training.phase_losses import LossWeights
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.vocoders.phase_model import PhaseModelShape

FFT_LENGTH = 256
HOP_LENGTH = 64
BIN_COUNT = FFT_LENGTH // 2 + 1
CHANNELS = 8
CROP_FRAMES = 64
CROP_COUNT = 4
LEARNING_RATE = 1e-3


class CropSet(Dataset[PhaseBatchItem]):
    """Magnitude-and-phase pairs long enough for the spectral term's widest analysis window.

    That term reads the waveform a phase produces at up to 2048 samples at a time, so a crop shorter
    than that has nothing for it to listen through.
    """

    def __init__(self, count: int = CROP_COUNT) -> None:
        self._count = count

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> PhaseBatchItem:
        generator = np.random.default_rng(index)
        angle = generator.uniform(-np.pi, np.pi, size=(BIN_COUNT, CROP_FRAMES))
        return (
            generator.random((BIN_COUNT, CROP_FRAMES)).astype(np.float32),
            np.cos(angle).astype(np.float32),
            np.sin(angle).astype(np.float32),
            0,
        )


@pytest.fixture(name="phase_module")
def fixture_phase_module() -> PhaseTrainingModule:
    torch.manual_seed(0)
    return PhaseTrainingModule(
        PhaseModelShape(bin_count=BIN_COUNT, channels=CHANNELS),
        fft_length=FFT_LENGTH,
        hop_length=HOP_LENGTH,
        learning_rate=LEARNING_RATE,
        weights=LossWeights(),
    )


@pytest.fixture(name="crop_loader")
def fixture_crop_loader() -> DataLoader[PhaseBatchItem]:
    return DataLoader(CropSet(), batch_size=2)


@pytest.fixture(name="fast_trainer")
def fixture_fast_trainer() -> Trainer:
    """One batch of each kind on the processor, writing nothing, so a test says only what it asks."""
    return Trainer(fast_dev_run=True, accelerator="cpu", logger=False, enable_checkpointing=False)


BAND_COUNT = 16
TIME_COLUMNS = 8
TEACHER_SIZE = 12
CACHED_SAMPLE_COUNT = 24
VIEW_COUNT = 2
LABELS = ("KICK: SOFT", "KICK: HARD", "SNARE", "SNARE, LO-FI", "BASS: SYNTH", "LEAD, SYNTH")


def write_grid_cache(directory: Path, *, sample_count: int = CACHED_SAMPLE_COUNT) -> GridCache:
    """A small cache whose grids say which of six sounds a sample is, plus a little noise per view."""
    generator = np.random.default_rng(0)
    grids = np.zeros((sample_count, 1 + VIEW_COUNT, BAND_COUNT, TIME_COLUMNS), dtype=np.float16)
    durations = np.zeros((sample_count, 1 + VIEW_COUNT), dtype=np.float32)
    for position in range(sample_count):
        kind = position % len(LABELS)
        pattern = np.zeros((BAND_COUNT, TIME_COLUMNS))
        pattern[kind * 2 : kind * 2 + 2] = 1.0
        # What tells one sample from another of its kind stays the same across its views.
        own = generator.normal(0.0, 0.2, pattern.shape)
        for view in range(1 + VIEW_COUNT):
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
        view_count=VIEW_COUNT,
        view_range_semitones=12.0,
        random_seed=0,
    )
    (directory / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(), encoding="utf-8")
    return open_grid_cache(directory)


def synthetic_corpus(directory: Path, *, labeled_share: int = 2) -> DescriptorCorpus:
    """The cache beside a teacher that already separates the six sounds, and a label on every `labeled_share`-th sample."""
    cache = write_grid_cache(directory)
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
