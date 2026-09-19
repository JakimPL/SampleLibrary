from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch
from lightning.pytorch import Trainer
from numpy.typing import NDArray
from torch.utils.data import DataLoader, Dataset

from samplemorph.features.shape import FeatureShape
from samplemorph.training.features.module import FeatureTrainingModule
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.refusals import ResumeRefused

SHAPE = FeatureShape(band_count=16, time_columns=8, latent_size=4, width=4, stage_count=2)
GRID_COUNT = 4
DYNAMIC_RANGE_DB = 100.0


class GridSet(Dataset[NDArray[np.float32]]):
    def __len__(self) -> int:
        return GRID_COUNT

    def __getitem__(self, index: int) -> NDArray[np.float32]:
        return np.random.default_rng(index).random((SHAPE.band_count, SHAPE.time_columns), dtype=np.float32)


def _module(critic_weight: float, *, critic_seed: int = 0) -> FeatureTrainingModule:
    """A module whose autoencoder starts the same whatever the critic, and whose critic starts from `critic_seed`."""
    torch.manual_seed(0)
    module = FeatureTrainingModule(
        SHAPE, settings=FeatureTrainingSettings(critic_weight=critic_weight), dynamic_range_db=DYNAMIC_RANGE_DB
    )
    torch.manual_seed(critic_seed)
    for parameter in module.critic.parameters():
        torch.nn.init.normal_(parameter)
    return module


def _trained_one_batch(module: FeatureTrainingModule) -> Trainer:
    trainer = Trainer(fast_dev_run=True, accelerator="cpu", logger=False, enable_checkpointing=False)
    loader = DataLoader(GridSet(), batch_size=GRID_COUNT)
    torch.manual_seed(1)
    trainer.fit(module, train_dataloaders=loader, val_dataloaders=loader)
    return trainer


def _autoencoder_state(module: FeatureTrainingModule) -> list[torch.Tensor]:
    return [parameter.detach().clone() for parameter in module.autoencoder.parameters()]


def test_at_weight_zero_the_critic_says_nothing_to_the_autoencoder() -> None:
    one, other = _module(0.0, critic_seed=0), _module(0.0, critic_seed=1)

    _trained_one_batch(one)
    _trained_one_batch(other)

    assert all(torch.equal(first, second) for first, second in zip(_autoencoder_state(one), _autoencoder_state(other)))


def test_above_weight_zero_the_critic_moves_the_autoencoder() -> None:
    one, other = _module(0.5, critic_seed=0), _module(0.5, critic_seed=1)

    _trained_one_batch(one)
    _trained_one_batch(other)

    assert not all(
        torch.equal(first, second) for first, second in zip(_autoencoder_state(one), _autoencoder_state(other))
    )


def test_both_optimizers_step_on_every_batch() -> None:
    module = _module(0.5)
    autoencoder_before = _autoencoder_state(module)
    critic_before = [parameter.detach().clone() for parameter in module.critic.parameters()]

    trainer = _trained_one_batch(module)

    assert trainer.global_step == 2
    assert not all(torch.equal(before, after) for before, after in zip(autoencoder_before, _autoencoder_state(module)))
    assert not all(torch.equal(before, after) for before, after in zip(critic_before, module.critic.parameters()))


def test_a_resume_point_is_continued_under_its_own_objective_alone() -> None:
    checkpoint: dict[str, Any] = {}
    _module(0.5).on_save_checkpoint(checkpoint)

    _module(0.5).on_load_checkpoint(checkpoint)
    with pytest.raises(ResumeRefused, match="continue"):
        _module(0.0).on_load_checkpoint(checkpoint)
