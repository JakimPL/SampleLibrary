from __future__ import annotations

import logging
from pathlib import Path

import pytest
import torch
from lightning.pytorch import LightningDataModule, Trainer
from torch.utils.data import DataLoader

from samplecore.tracking.silent import SilentRun
from sampledescriptor.training.export import BEST_LOSS_STATE, BestEpochExport
from sampledescriptor.training.metrics import DESCRIPTOR_MONITORED_METRIC
from sampledescriptor.training.refusals import ResumeRefused
from sampledescriptor.training.run.execution import (
    RunPlacement,
    SameDirectoryCheckpointIO,
    check_resume_point,
    fit_and_export,
    geometry_parameters,
    resume_checkpoint,
)
from sampledescriptor.training.run.paths import (
    RunFamily,
    RunFinished,
    finished_record_path,
    read_run_finished,
    resume_path,
    run_directory,
)
from sampledescriptor.training.run.settings import RunSettings
from samplemorph.geometry import log_frequency_geometry
from tests.sampledescriptor.training.conftest import TinyBatch, TinyModule


def test_the_recorded_parameters_name_what_tells_one_grid_from_another() -> None:
    geometry = log_frequency_geometry()

    parameters = geometry_parameters(geometry)

    assert {
        "geometry",
        "anchor",
        "analysis_window",
        "fft_length",
        "hop_length",
        "bins_per_octave",
        "band_count",
    } <= set(parameters)
    assert parameters["geometry"] == geometry.kind
    assert parameters["anchor"] == geometry.anchor.value
    assert all(isinstance(value, str) for value in parameters.values())


def test_continuing_a_run_that_never_stopped_anywhere_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ResumeRefused, match="--resume continues from"):
        check_resume_point(tmp_path, family=RunFamily.DESCRIPTOR, name="absent", resume=True)


def test_a_fresh_run_over_a_resume_point_says_it_replaces_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    stored = resume_path(tmp_path, family=RunFamily.DESCRIPTOR, name="again")
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"checkpoint")

    with caplog.at_level(logging.WARNING):
        check_resume_point(tmp_path, family=RunFamily.DESCRIPTOR, name="again", resume=False)

    assert "replaces the resume point" in caplog.text


def _trainer(directory: Path, *, max_epochs: int, export: BestEpochExport) -> Trainer:
    return Trainer(
        max_epochs=max_epochs,
        limit_train_batches=1,
        limit_val_batches=1,
        accelerator="cpu",
        logger=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        num_sanity_val_steps=0,
        callbacks=[export, resume_checkpoint(directory)],
        plugins=[SameDirectoryCheckpointIO()],
    )


def _export(path: Path, written: list[float]) -> BestEpochExport:
    return BestEpochExport(
        path=path,
        monitored=DESCRIPTOR_MONITORED_METRIC,
        tracker=SilentRun(),
        writer=lambda record: written.append(record.best_validation_loss),
    )


def test_a_resumed_run_continues_from_the_epoch_it_stopped_at_with_its_best_score(
    tmp_path: Path, tiny_loader: DataLoader[TinyBatch]
) -> None:
    """The resume point is the latest epoch whatever it scored, and carries the best score exported before it."""
    first_writes: list[float] = []
    first = _export(tmp_path / "model.pt", first_writes)
    torch.manual_seed(0)
    module = TinyModule(learning_rate=1e-3)
    _trainer(tmp_path, max_epochs=2, export=first).fit(
        module, train_dataloaders=tiny_loader, val_dataloaders=tiny_loader
    )
    stored = torch.load(tmp_path / "resume.ckpt", map_location="cpu", weights_only=False)

    assert stored["epoch"] == 1
    assert stored["callbacks"][first.state_key] == {BEST_LOSS_STATE: first.best_loss}
    assert not list(tmp_path.glob("*.partial"))

    second_writes: list[float] = []
    second = _export(tmp_path / "model.pt", second_writes)
    resumed = _trainer(tmp_path, max_epochs=3, export=second)
    resumed.fit(
        module,
        train_dataloaders=tiny_loader,
        val_dataloaders=tiny_loader,
        ckpt_path=str(tmp_path / "resume.ckpt"),
    )

    assert resumed.current_epoch == 3
    assert second.best_loss <= first.best_loss
    assert all(loss < first.best_loss for loss in second_writes)


class TinyData(LightningDataModule):
    """The same crops for training and validation, in the shape `fit_and_export` takes a run's data."""

    def __init__(self, loader: DataLoader[TinyBatch]) -> None:
        super().__init__()
        self._loader = loader

    def train_dataloader(self) -> DataLoader[TinyBatch]:
        return self._loader

    def val_dataloader(self) -> DataLoader[TinyBatch]:
        return self._loader


class StoppingModule(TinyModule):
    """A module whose second epoch breaks off, the way a run a machine stops never reaches its end."""

    def training_step(self, batch: TinyBatch, batch_index: int) -> torch.Tensor:
        if self.current_epoch >= 1:
            raise RuntimeError("the run stopped")
        return super().training_step(batch, batch_index)


def _placement(library_root: Path) -> RunPlacement:
    return RunPlacement(
        library_root=library_root,
        family=RunFamily.DESCRIPTOR,
        model_name="finishing",
        tracker=SilentRun(),
        resume=False,
    )


def test_a_run_reaching_its_last_epoch_records_that_it_finished(
    tmp_path: Path, tiny_loader: DataLoader[TinyBatch]
) -> None:
    placement = _placement(tmp_path)
    module = TinyModule(learning_rate=1e-3)

    outcome = fit_and_export(
        module,
        TinyData(tiny_loader),
        export=_export(tmp_path / "model.pt", []),
        settings=RunSettings(epochs=2, batch_size=2, worker_count=0, accelerator="cpu"),
        placement=placement,
    )

    finished = read_run_finished(tmp_path, family=RunFamily.DESCRIPTOR, name="finishing")
    assert finished == RunFinished(epochs_completed=2, best_validation_loss=outcome.best_validation_loss)


def test_a_run_that_stops_before_its_last_epoch_leaves_no_record_of_an_earlier_finish(
    tmp_path: Path, tiny_loader: DataLoader[TinyBatch]
) -> None:
    stale = finished_record_path(tmp_path, family=RunFamily.DESCRIPTOR, name="finishing")
    stale.parent.mkdir(parents=True)
    stale.write_text(RunFinished(epochs_completed=9, best_validation_loss=0.5).model_dump_json(), encoding="utf-8")
    module = StoppingModule(learning_rate=1e-3)

    with pytest.raises(RuntimeError, match="the run stopped"):
        fit_and_export(
            module,
            TinyData(tiny_loader),
            export=_export(tmp_path / "model.pt", []),
            settings=RunSettings(epochs=3, batch_size=2, worker_count=0, accelerator="cpu"),
            placement=_placement(tmp_path),
        )

    assert read_run_finished(tmp_path, family=RunFamily.DESCRIPTOR, name="finishing") is None
