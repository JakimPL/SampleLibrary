from __future__ import annotations

from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplemorph.training.metrics import LOGGED_METRICS, MONITORED_METRIC, VALIDATION_LOSS
from samplemorph.training.phase_dataset import PhaseBatchItem
from samplemorph.training.phase_module import PhaseTrainingModule
from tests.samplemorph.training.conftest import FFT_LENGTH


def test_the_metric_the_checkpoint_watches_is_one_the_module_logs() -> None:
    """A monitored name the module never logs leaves a run silently keeping no best epoch."""
    assert MONITORED_METRIC in LOGGED_METRICS


def test_one_pass_reports_the_metrics_a_run_is_judged_by(
    phase_module: PhaseTrainingModule, crop_loader: DataLoader[PhaseBatchItem], fast_trainer: Trainer
) -> None:
    fast_trainer.fit(phase_module, train_dataloaders=crop_loader, val_dataloaders=crop_loader)

    assert VALIDATION_LOSS in fast_trainer.callback_metrics


def test_the_analysis_taper_travels_with_the_module(phase_module: PhaseTrainingModule) -> None:
    """Registering the taper is what puts it on the step's own device rather than the builder's."""
    assert "taper" in dict(phase_module.named_buffers())
    assert phase_module.taper.shape == (FFT_LENGTH,)


def test_the_rate_falls_over_the_whole_run_rather_than_over_each_epoch(
    phase_module: PhaseTrainingModule, crop_loader: DataLoader[PhaseBatchItem], fast_trainer: Trainer
) -> None:
    fast_trainer.fit(phase_module, train_dataloaders=crop_loader, val_dataloaders=crop_loader)

    configured = phase_module.configure_optimizers()

    assert configured["lr_scheduler"]["interval"] == "step"
