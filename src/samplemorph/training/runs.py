from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lightning.pytorch import LightningDataModule, LightningModule, Trainer
from lightning.pytorch.callbacks import ModelCheckpoint
from lightning.pytorch.loggers import CSVLogger

from samplecore.tracking import TrackedRun
from samplemorph.training.export import BestEpochExport
from samplemorph.training.run_settings import GRADIENT_CLIP, RunSettings
from samplemorph.training.tracked_logger import TrackedRunLogger

RUNS_DIRECTORY_NAME: Final[str] = "runs"
LAST_CHECKPOINT_NAME: Final[str] = "last"


@dataclass(frozen=True)
class TrainingOutcome:
    """What one run left behind: its best epoch, and where each of its two files sits."""

    best_validation_loss: float
    epochs_completed: int
    model_path: Path
    resume_path: Path


def run_directory(library_root: Path, *, name: str) -> Path:
    """Where one run's metrics and resume points are kept, beside the library rather than the repo."""
    return library_root / RUNS_DIRECTORY_NAME / name


def resume_path(library_root: Path, *, name: str) -> Path:
    """The checkpoint an interrupted run of this name picks up from."""
    return run_directory(library_root, name=name) / f"{LAST_CHECKPOINT_NAME}.ckpt"


def last_checkpoint(directory: Path, *, monitored: str) -> ModelCheckpoint:
    """The resume point, rewritten each epoch so an interrupted run loses at most that epoch."""
    return ModelCheckpoint(
        dirpath=directory,
        filename=LAST_CHECKPOINT_NAME,
        monitor=monitored,
        mode="min",
        save_top_k=1,
        save_last=True,
        enable_version_counter=False,
    )


@dataclass(frozen=True)
class RunPlacement:
    """Where one named run keeps its files, which record it reports to, and whether it picks up where it stopped."""

    library_root: Path
    model_name: str
    tracker: TrackedRun
    resume: bool

    @property
    def directory(self) -> Path:
        return run_directory(self.library_root, name=self.model_name)

    @property
    def resume_path(self) -> Path:
        return resume_path(self.library_root, name=self.model_name)


def fit_and_export(
    module: LightningModule,
    data: LightningDataModule,
    *,
    export: BestEpochExport,
    settings: RunSettings,
    placement: RunPlacement,
) -> TrainingOutcome:
    """Drive one run to its end: the trainer, its three loggers, its resume point, and what it left behind.

    Two files come out, for two different purposes. The trainer's own checkpoint carries the
    optimizer, the schedule and the epoch reached, so a run cut short continues from where it
    stopped. The export carries the network alone, which is what a reader of the model loads.
    """
    trainer = Trainer(
        max_epochs=settings.epochs,
        accelerator=settings.accelerator,
        precision=settings.precision,
        gradient_clip_val=GRADIENT_CLIP,
        default_root_dir=placement.directory,
        logger=[CSVLogger(save_dir=placement.directory, name=""), TrackedRunLogger(placement.tracker)],
        callbacks=[export, last_checkpoint(placement.directory, monitored=export.monitored)],
    )
    started_from = placement.resume_path
    trainer.fit(
        module, datamodule=data, ckpt_path=str(started_from) if placement.resume and started_from.is_file() else None
    )
    return TrainingOutcome(
        best_validation_loss=export.best_loss,
        epochs_completed=trainer.current_epoch,
        model_path=export.path,
        resume_path=started_from,
    )
