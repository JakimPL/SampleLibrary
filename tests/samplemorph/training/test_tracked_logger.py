from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplecore.tracking import TrackedRun
from samplemorph.training.metrics import VALIDATION_LOSS
from samplemorph.training.phase_dataset import PhaseBatchItem
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.training.tracked_logger import TrackedRunLogger

RUN_ID = "a-run"


@dataclass
class RecordingRun:
    """A TrackedRun keeping what it was told, so a test can read it back."""

    metrics: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, str] = field(default_factory=dict)
    artifacts: list[Path] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        return RUN_ID

    def log_parameters(self, parameters: dict[str, str]) -> None:
        self.parameters.update(parameters)

    def log_metrics(self, metrics: dict[str, float], *, step: int) -> None:
        self.metrics.update(metrics)

    def log_artifact(self, path: Path) -> None:
        self.artifacts.append(path)


def test_a_recording_run_is_a_tracked_run() -> None:
    run: TrackedRun = RecordingRun()

    assert run.run_id == RUN_ID


def test_the_trainer_reports_what_it_measures_to_the_run(
    phase_module: PhaseTrainingModule, crop_loader: DataLoader[PhaseBatchItem]
) -> None:
    """The run the command opened is where a pass's numbers belong, however the trainer names them."""
    run = RecordingRun()
    # fast_dev_run swaps in a logger of its own, so a run that reports must be a real short one.
    trainer = Trainer(
        max_epochs=1,
        limit_train_batches=1,
        limit_val_batches=1,
        accelerator="cpu",
        logger=TrackedRunLogger(run),
        enable_checkpointing=False,
        enable_progress_bar=False,
    )

    trainer.fit(phase_module, train_dataloaders=crop_loader, val_dataloaders=crop_loader)

    assert VALIDATION_LOSS in run.metrics


def test_a_logger_reports_the_run_it_writes_to_as_its_version() -> None:
    """Lightning names a log directory after the version, so a run's own identity is the useful one."""
    assert TrackedRunLogger(RecordingRun()).version == RUN_ID
