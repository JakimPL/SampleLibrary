from __future__ import annotations

from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.models.base import FROZEN

RUNS_DIRECTORY_NAME: Final[str] = "runs"
RESUME_CHECKPOINT_NAME: Final[str] = "resume"
CHECKPOINT_SUFFIX: Final[str] = ".ckpt"
FINISHED_RECORD_NAME: Final[str] = "finished.json"


@unique
class RunFamily(StrEnum):
    """Which kind of network a run teaches, which keeps runs of one name in different families apart."""

    CODEC = "codec"
    DESCRIPTOR = "descriptor"
    FEATURES = "features"
    RESTORER = "restorer"


class RunFinished(BaseModel):
    """What a run that reached its last epoch records beside its files: how far it went and the best score it kept.

    It is written once the trainer finishes every epoch it was asked for, and removed when a run of
    the same name starts again, so a model file standing beside it is the complete outcome of that
    run rather than an epoch a stopped run happened to export.
    """

    model_config = FROZEN

    epochs_completed: int
    best_validation_loss: float


def finished_record_path(library_root: Path, *, family: RunFamily, name: str) -> Path:
    """Where a run that reached its last epoch records that it did."""
    return run_directory(library_root, family=family, name=name) / FINISHED_RECORD_NAME


def read_run_finished(library_root: Path, *, family: RunFamily, name: str) -> RunFinished | None:
    """The record of a run that reached its last epoch, or ``None`` for a run that has not, or never ran."""
    path = finished_record_path(library_root, family=family, name=name)
    if not path.is_file():
        return None
    return RunFinished.model_validate_json(path.read_text(encoding="utf-8"))


def run_directory(library_root: Path, *, family: RunFamily, name: str) -> Path:
    """Where one run's metrics and resume point are kept, beside the library rather than the repo."""
    return library_root / RUNS_DIRECTORY_NAME / family.value / name


def resume_path(library_root: Path, *, family: RunFamily, name: str) -> Path:
    """The checkpoint an interrupted run of this name picks up from."""
    return run_directory(library_root, family=family, name=name) / f"{RESUME_CHECKPOINT_NAME}{CHECKPOINT_SUFFIX}"
