from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lightning.pytorch import Trainer, seed_everything
from lightning.pytorch.callbacks import ModelCheckpoint
from lightning.pytorch.loggers import CSVLogger

from samplemorph.geometry import fourier_bin_count
from samplemorph.training.metrics import MONITORED_METRIC
from samplemorph.training.phase_data import PhaseCorpus, PhaseDataModule
from samplemorph.training.phase_export import PhaseExport
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.training.settings import GRADIENT_CLIP, TrainingSettings
from samplemorph.vocoders.learned import phase_model_path
from samplemorph.vocoders.phase_model import PhaseModelShape

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


def run_phase_training(
    corpus: PhaseCorpus,
    *,
    settings: TrainingSettings,
    model_name: str,
    accelerator: str,
    resume: bool,
) -> TrainingOutcome:
    """Teach a phase model, writing what it learns as it learns it.

    Two files come out, for two different purposes. The trainer's own checkpoint carries the
    optimizer, the schedule and the epoch reached, so a run cut short by a crash continues from
    where it stopped. The exported weights carry the network alone, which is what a vocoder reads
    and what makes a run listenable while it is still going.
    """
    seed_everything(settings.random_seed, workers=True)
    library_root = corpus.library_root
    geometry = corpus.canonicalizer.geometry
    data = PhaseDataModule(
        corpus,
        batch_size=settings.batch_size,
        crop_frames=settings.crop_frames,
        worker_count=settings.worker_count,
        random_seed=settings.random_seed,
    )
    module = PhaseTrainingModule(
        PhaseModelShape(bin_count=fourier_bin_count(fft_length=geometry.fft_length), channels=settings.channels),
        fft_length=geometry.fft_length,
        hop_length=geometry.hop_length,
        learning_rate=settings.learning_rate,
        weights=settings.weights,
    )
    export = PhaseExport(
        module,
        path=phase_model_path(library_root, name=model_name),
        corpus=corpus,
        trained_sample_count=data.training_sample_count,
    )
    directory = run_directory(library_root, name=model_name)
    trainer = Trainer(
        max_epochs=settings.epochs,
        accelerator=accelerator,
        precision=settings.precision,
        gradient_clip_val=GRADIENT_CLIP,
        default_root_dir=directory,
        logger=CSVLogger(save_dir=directory, name=""),
        callbacks=[export, _checkpoint(directory)],
    )
    started_from = resume_path(library_root, name=model_name)
    trainer.fit(module, datamodule=data, ckpt_path=str(started_from) if resume and started_from.is_file() else None)
    return TrainingOutcome(
        best_validation_loss=export.best_loss,
        epochs_completed=trainer.current_epoch,
        model_path=export.path,
        resume_path=started_from,
    )


def _checkpoint(directory: Path) -> ModelCheckpoint:
    """The resume point, rewritten each epoch so an interrupted run loses at most that epoch."""
    return ModelCheckpoint(
        dirpath=directory,
        filename=LAST_CHECKPOINT_NAME,
        monitor=MONITORED_METRIC,
        mode="min",
        save_top_k=1,
        save_last=True,
        enable_version_counter=False,
    )
