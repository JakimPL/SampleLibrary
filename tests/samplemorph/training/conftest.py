from __future__ import annotations

import numpy as np
import pytest
import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader, Dataset

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
