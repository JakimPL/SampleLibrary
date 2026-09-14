from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from lightning.fabric.plugins import TorchCheckpointIO
from lightning.pytorch import LightningDataModule, LightningModule, Trainer, seed_everything
from lightning.pytorch.callbacks import ModelCheckpoint
from lightning.pytorch.loggers import CSVLogger

from samplecore.storage.atomic import write_atomically, write_bytes_atomically
from samplecore.tracking import TrackedRun
from samplemorph.geometry import ConstantQGeometry, Geometry, LogFrequencyGeometry, MelGeometry
from samplemorph.training.descriptor_cache import GridCache
from samplemorph.training.export import BestEpochExport
from samplemorph.training.progress import ProgressLines
from samplemorph.training.refusals import ResumeRefused
from samplemorph.training.run_paths import (
    RESUME_CHECKPOINT_NAME,
    RunFamily,
    RunFinished,
    finished_record_path,
    resume_path,
    run_directory,
)
from samplemorph.training.run_settings import GRADIENT_CLIP, RunSettings
from samplemorph.training.tracked_logger import TrackedRunLogger

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingOutcome:
    """What one run left behind: its best epoch, and where each of its two files sits."""

    best_validation_loss: float
    epochs_completed: int
    model_path: Path
    resume_path: Path

    @property
    def exported(self) -> bool:
        """Whether an epoch finished validation with a score, which is what writes the model."""
        return math.isfinite(self.best_validation_loss)


def check_resume_point(library_root: Path, *, family: RunFamily, name: str, resume: bool) -> None:
    """Make sure a continued run has a point to continue from, and say when a fresh run replaces one.

    Raises:
        ResumeRefused: the run was asked to continue and no resume point is stored for it.
    """
    path = resume_path(library_root, family=family, name=name)
    if resume and not path.is_file():
        raise ResumeRefused(f"--resume continues from {path}, and no run of that name stopped there")
    if not resume and path.is_file():
        _logger.warning("A fresh run replaces the resume point at %s; pass --resume to continue it instead.", path)


def resume_checkpoint(directory: Path) -> ModelCheckpoint:
    """The resume point, rewritten after every epoch so an interrupted run loses at most the epoch it was in.

    Nothing is monitored, so the latest epoch is kept whatever it scored; the best epoch lives in
    the exported model instead.
    """
    return ModelCheckpoint(
        dirpath=directory,
        filename=RESUME_CHECKPOINT_NAME,
        monitor=None,
        save_top_k=1,
        save_last=False,
        every_n_epochs=1,
        save_on_train_epoch_end=True,
        enable_version_counter=False,
    )


class SameDirectoryCheckpointIO(TorchCheckpointIO):
    """Writes each checkpoint beside its destination and moves it into place whole.

    An interruption while the resume point is being rewritten leaves the previous one readable.
    """

    def save_checkpoint(
        self, checkpoint: dict[str, Any], path: str | Path, storage_options: object | None = None
    ) -> None:
        del storage_options
        write_atomically(Path(path), lambda stream: torch.save(checkpoint, stream))


@dataclass(frozen=True)
class RunPlacement:
    """Where one named run keeps its files, which record it reports to, and whether it picks up where it stopped."""

    library_root: Path
    family: RunFamily
    model_name: str
    tracker: TrackedRun
    resume: bool

    @property
    def directory(self) -> Path:
        return run_directory(self.library_root, family=self.family, name=self.model_name)

    @property
    def resume_path(self) -> Path:
        return resume_path(self.library_root, family=self.family, name=self.model_name)


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
    optimizer, the schedule, the epoch reached and the best score exported so far, so a run cut
    short continues from the epoch it stopped at. The export carries the network alone, which is
    what a reader of the model loads. Progress reaches the log as lines throughout, and the
    progress bar draws on a terminal. A run that finishes every epoch with a model exported writes
    a `RunFinished` record beside them.
    """
    trainer = Trainer(
        max_epochs=settings.epochs,
        accelerator=settings.accelerator,
        precision=settings.precision,
        gradient_clip_val=GRADIENT_CLIP,
        default_root_dir=placement.directory,
        logger=[CSVLogger(save_dir=placement.directory, name=""), TrackedRunLogger(placement.tracker)],
        callbacks=[export, resume_checkpoint(placement.directory), ProgressLines()],
        plugins=[SameDirectoryCheckpointIO()],
        enable_progress_bar=sys.stdout.isatty(),
    )
    finished_path = finished_record_path(placement.library_root, family=placement.family, name=placement.model_name)
    finished_path.unlink(missing_ok=True)
    trainer.fit(module, datamodule=data, ckpt_path=str(placement.resume_path) if placement.resume else None)
    if trainer.state.finished and math.isfinite(export.best_loss):
        record = RunFinished(epochs_completed=trainer.current_epoch, best_validation_loss=export.best_loss)
        write_bytes_atomically(finished_path, record.model_dump_json().encode("utf-8"))
    return TrainingOutcome(
        best_validation_loss=export.best_loss,
        epochs_completed=trainer.current_epoch,
        model_path=export.path,
        resume_path=placement.resume_path,
    )


def begin_cached_run(
    placement: RunPlacement, *, settings: RunSettings, parameters: dict[str, str], cache: GridCache
) -> None:
    """Seed the run and record what it was asked to do and which cache it reads, before the first epoch.

    A pass that ends badly is then still identifiable by what it ran under.
    """
    seed_everything(settings.random_seed, workers=True)
    placement.tracker.log_parameters(
        parameters
        | {"cache": cache.directory.name, "canonicalizer": cache.description.canonicalizer}
        | geometry_parameters(cache.description.geometry)
    )


def geometry_parameters(geometry: Geometry) -> dict[str, str]:
    """The analysis a run was made on, in the form a tracker records.

    Two runs on two grids are then told apart in the record by the grid itself: its axis, its
    anchor, its window and hop, and how finely it reads frequency.
    """
    shared = {
        "geometry": geometry.kind,
        "anchor": geometry.anchor.value,
        "fft_length": str(geometry.fft_length),
        "hop_length": str(geometry.hop_length),
        "band_count": str(geometry.band_count),
    }
    match geometry:
        case LogFrequencyGeometry():
            return shared | {
                "analysis_window": geometry.analysis_window.value,
                "bins_per_octave": str(geometry.bins_per_octave),
            }
        case ConstantQGeometry():
            return shared | {"bins_per_octave": str(geometry.bins_per_octave)}
        case MelGeometry():
            return shared
