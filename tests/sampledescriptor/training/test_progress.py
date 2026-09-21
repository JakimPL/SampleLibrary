from __future__ import annotations

import logging

import pytest
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from sampledescriptor.training.progress import ProgressLines
from tests.sampledescriptor.training.conftest import TinyBatch, TinyModule

LOGGER_NAME = "sampledescriptor.training.progress"


def test_progress_lines_report_the_batch_reached_and_the_validation_readings(
    tiny_module: TinyModule,
    tiny_loader: DataLoader[TinyBatch],
    caplog: pytest.LogCaptureFixture,
) -> None:
    trainer = Trainer(
        fast_dev_run=True,
        accelerator="cpu",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        callbacks=[ProgressLines(interval_seconds=0.0)],
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        trainer.fit(tiny_module, train_dataloaders=tiny_loader, val_dataloaders=tiny_loader)

    messages = [record.getMessage() for record in caplog.records if record.name == LOGGER_NAME]
    assert any("batch 1 of 1" in message and "training/loss" in message for message in messages)
    assert any("validated" in message and "validation/loss" in message for message in messages)
