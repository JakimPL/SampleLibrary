from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch
from lightning.pytorch import Trainer
from numpy.typing import NDArray
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.training.pitch.augmentation import FrameAugmentation
from samplemorph.training.pitch.data import HeldOutItem
from samplemorph.training.pitch.module import PitchTrainingModule
from samplemorph.training.pitch.settings import AugmentationSettings, PitchTrainingSettings
from samplemorph.training.refusals import ResumeRefused

SHAPE = PitchHeadShape(band_count=48, bins_per_octave=36, shift_reach_bins=9, channels=(4, 6), kernel_size=5)
FRAME_RANGE_DB = 60.0
BATCH = 4
KEPT_FRAMES = 2
PEAK_BIN = 24
OCTAVE_BINS = 36
RETUNING_SEMITONES = 2.0


def _frame(peak_bin: int) -> NDArray[np.float32]:
    frame = np.zeros(SHAPE.band_count, dtype=np.float32)
    frame[peak_bin] = 1.0
    frame[min(peak_bin + OCTAVE_BINS, SHAPE.band_count - 1)] = 0.6
    return frame


class FrameSet(Dataset[NDArray[np.float32]]):
    """One frame each, standing a few bins apart, which is what a training step crops and shifts."""

    def __len__(self) -> int:
        return BATCH

    def __getitem__(self, index: int) -> NDArray[np.float32]:
        return _frame(PEAK_BIN + index)


class HeldOutSet(Dataset[HeldOutItem]):
    """Each sample as stored and truly retuned, with the retuning between them."""

    def __len__(self) -> int:
        return BATCH

    def __getitem__(self, index: int) -> HeldOutItem:
        moved = int(round(RETUNING_SEMITONES * SHAPE.bins_per_semitone))
        stored = np.stack([_frame(PEAK_BIN + index)] * KEPT_FRAMES)
        retuned = np.stack([_frame(PEAK_BIN + index + moved)] * KEPT_FRAMES)
        return stored, KEPT_FRAMES, retuned, KEPT_FRAMES, RETUNING_SEMITONES


def _settings(invariance_weight: float) -> PitchTrainingSettings:
    return PitchTrainingSettings(shift_reach_semitones=3.0, invariance_weight=invariance_weight)


def _module(invariance_weight: float) -> PitchTrainingModule:
    torch.manual_seed(0)
    return PitchTrainingModule(SHAPE, settings=_settings(invariance_weight), frame_range_db=FRAME_RANGE_DB)


def _frames() -> Tensor:
    return torch.from_numpy(np.stack([_frame(PEAK_BIN + index) for index in range(BATCH)]))


def test_a_step_reads_three_views_of_every_frame_and_moves_the_network() -> None:
    module = _module(1.0)
    before = [parameter.detach().clone() for parameter in module.network.parameters()]
    trainer = Trainer(fast_dev_run=True, accelerator="cpu", logger=False, enable_checkpointing=False)
    torch.manual_seed(1)

    trainer.fit(
        module,
        train_dataloaders=DataLoader(FrameSet(), batch_size=BATCH),
        val_dataloaders=DataLoader(HeldOutSet(), batch_size=BATCH),
    )

    assert trainer.global_step == 1
    assert not all(
        torch.equal(first, second) for first, second in zip(before, module.network.parameters(), strict=True)
    )


def test_a_resume_point_is_continued_under_its_own_objective_alone() -> None:
    checkpoint: dict[str, Any] = {}
    _module(1.0).on_save_checkpoint(checkpoint)

    _module(1.0).on_load_checkpoint(checkpoint)
    with pytest.raises(ResumeRefused, match="continue"):
        _module(0.0).on_load_checkpoint(checkpoint)


def test_an_augmented_frame_keeps_its_partials_where_they_stood_and_reads_on_the_analysis_s_own_scale() -> None:
    augment = FrameAugmentation(settings=AugmentationSettings(), frame_range_db=FRAME_RANGE_DB)
    torch.manual_seed(0)
    frames = _frames()

    augmented = augment(frames)

    assert augmented.shape == frames.shape
    assert float(augmented.min()) >= 0.0
    assert float(augmented.max()) == pytest.approx(1.0)
    assert all(float(row[PEAK_BIN + index]) > float(row[PEAK_BIN + index + 6]) for index, row in enumerate(augmented))
