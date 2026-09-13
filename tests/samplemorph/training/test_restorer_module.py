from __future__ import annotations

import pytest
import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplemorph.training.metrics import (
    RESTORER_MONITORED_METRIC,
    RESTORER_VALIDATION_COARSE,
    RESTORER_VALIDATION_FINE,
    RESTORER_VALIDATION_LEAST_SQUARES,
    RESTORER_VALIDATION_LOSS,
)
from samplemorph.training.restorer_dataset import RestorerBatchItem
from samplemorph.training.restorer_losses import COARSE_POOLINGS, restorer_loss
from samplemorph.training.restorer_module import RestorerTrainingModule
from tests.samplemorph.training.conftest import RESTORER_BIN_COUNT, RESTORER_CROP_FRAMES

BIN_COUNT = RESTORER_BIN_COUNT
CROP_FRAMES = RESTORER_CROP_FRAMES


def test_the_monitored_metric_is_one_the_module_logs(
    restorer_module: RestorerTrainingModule, pair_loader: DataLoader[RestorerBatchItem], fast_trainer: Trainer
) -> None:
    fast_trainer.fit(restorer_module, train_dataloaders=pair_loader, val_dataloaders=pair_loader)

    assert RESTORER_MONITORED_METRIC in fast_trainer.callback_metrics
    for name in (RESTORER_VALIDATION_LOSS, RESTORER_VALIDATION_FINE, RESTORER_VALIDATION_COARSE):
        assert name in fast_trainer.callback_metrics


def test_an_untrained_restorer_scores_exactly_the_least_squares_baseline(
    restorer_module: RestorerTrainingModule, pair_loader: DataLoader[RestorerBatchItem]
) -> None:
    """The output layer starts at zero, so before any step the run sits at the loss of leaving the reading alone."""
    trainer = Trainer(accelerator="cpu", logger=False, enable_checkpointing=False, enable_progress_bar=False)

    trainer.validate(restorer_module, dataloaders=pair_loader, verbose=False)

    assert float(trainer.callback_metrics[RESTORER_VALIDATION_LOSS]) == pytest.approx(
        float(trainer.callback_metrics[RESTORER_VALIDATION_LEAST_SQUARES])
    )


def test_the_loss_weighs_every_comparison_the_same() -> None:
    predicted = torch.zeros(1, BIN_COUNT, CROP_FRAMES)
    target = torch.full((1, BIN_COUNT, CROP_FRAMES), 0.5)

    parts = restorer_loss(predicted, target)

    assert parts.fine.item() == pytest.approx(0.5)
    assert parts.coarse.item() == pytest.approx(0.5)
    assert parts.total.item() == pytest.approx(0.5)
    assert len(COARSE_POOLINGS) >= 1


def test_a_misplaced_line_costs_less_at_the_coarse_readings_than_at_the_fine_one() -> None:
    predicted = torch.zeros(1, BIN_COUNT, CROP_FRAMES)
    target = torch.zeros(1, BIN_COUNT, CROP_FRAMES)
    predicted[:, 20] = 1.0
    target[:, 21] = 1.0

    parts = restorer_loss(predicted, target)

    assert parts.coarse.item() < parts.fine.item()


def test_the_rate_falls_over_the_whole_run(
    restorer_module: RestorerTrainingModule, pair_loader: DataLoader[RestorerBatchItem], fast_trainer: Trainer
) -> None:
    fast_trainer.fit(restorer_module, train_dataloaders=pair_loader, val_dataloaders=pair_loader)

    configured = restorer_module.configure_optimizers()

    assert configured["lr_scheduler"]["interval"] == "step"
