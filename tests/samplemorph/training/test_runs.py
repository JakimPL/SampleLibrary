from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest
import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplecore.tracking.silent import SilentRun
from samplemorph.geometry import Geometry, constant_q_geometry, log_frequency_geometry, mel_geometry
from samplemorph.training.export import BEST_LOSS_STATE, BestEpochExport
from samplemorph.training.metrics import RESTORER_MONITORED_METRIC
from samplemorph.training.refusals import ResumeRefused
from samplemorph.training.restorer_dataset import RestorerBatchItem
from samplemorph.training.restorer_module import RestorerTrainingModule
from samplemorph.training.runs import (
    RunFamily,
    SameDirectoryCheckpointIO,
    check_resume_point,
    geometry_parameters,
    resume_checkpoint,
    resume_path,
    run_directory,
)
from samplemorph.vocoders.restorer_model import RestorerShape
from tests.samplemorph.training.conftest import RESTORER_CHANNELS


@dataclass(frozen=True)
class GeometryCase:
    """One axis and the names its recorded parameters must and must not carry."""

    name: str
    geometry: Geometry
    named: tuple[str, ...]
    unnamed: tuple[str, ...]


GEOMETRY_CASES = (
    GeometryCase(
        name="log_frequency",
        geometry=log_frequency_geometry(),
        named=("geometry", "anchor", "analysis_window", "fft_length", "hop_length", "bins_per_octave", "band_count"),
        unnamed=(),
    ),
    GeometryCase(
        name="constant_q",
        geometry=constant_q_geometry(),
        named=("geometry", "anchor", "fft_length", "hop_length", "bins_per_octave", "band_count"),
        unnamed=("analysis_window",),
    ),
    GeometryCase(
        name="mel",
        geometry=mel_geometry(),
        named=("geometry", "anchor", "fft_length", "hop_length", "band_count"),
        unnamed=("analysis_window", "bins_per_octave"),
    ),
)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_recorded_parameters_name_what_tells_one_grid_from_another(case: GeometryCase) -> None:
    parameters = geometry_parameters(case.geometry)

    assert set(case.named) <= set(parameters)
    assert not set(case.unnamed) & set(parameters)
    assert parameters["geometry"] == case.geometry.kind
    assert parameters["anchor"] == case.geometry.anchor.value
    assert all(isinstance(value, str) for value in parameters.values())


def test_runs_of_one_name_in_different_families_keep_apart(tmp_path: Path) -> None:
    directories = {run_directory(tmp_path, family=family, name="shared") for family in RunFamily}

    assert len(directories) == len(RunFamily)
    assert resume_path(tmp_path, family=RunFamily.CODEC, name="shared").name == "resume.ckpt"


def test_continuing_a_run_that_never_stopped_anywhere_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ResumeRefused, match="--resume continues from"):
        check_resume_point(tmp_path, family=RunFamily.RESTORER, name="absent", resume=True)


def test_a_fresh_run_over_a_resume_point_says_it_replaces_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    stored = resume_path(tmp_path, family=RunFamily.RESTORER, name="again")
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"checkpoint")

    with caplog.at_level(logging.WARNING):
        check_resume_point(tmp_path, family=RunFamily.RESTORER, name="again", resume=False)

    assert "replaces the resume point" in caplog.text


def _restorer_trainer(directory: Path, *, max_epochs: int, export: BestEpochExport) -> Trainer:
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
        monitored=RESTORER_MONITORED_METRIC,
        tracker=SilentRun(),
        writer=lambda record: written.append(record.best_validation_loss),
    )


def test_a_resumed_run_continues_from_the_epoch_it_stopped_at_with_its_best_score(
    tmp_path: Path, pair_loader: DataLoader[RestorerBatchItem]
) -> None:
    """The resume point is the latest epoch whatever it scored, and carries the best score exported before it."""
    first_writes: list[float] = []
    first = _export(tmp_path / "model.pt", first_writes)
    torch.manual_seed(0)
    module = RestorerTrainingModule(RestorerShape(channels=RESTORER_CHANNELS, dilations=(1, 2)), learning_rate=1e-3)
    _restorer_trainer(tmp_path, max_epochs=2, export=first).fit(
        module, train_dataloaders=pair_loader, val_dataloaders=pair_loader
    )
    stored = torch.load(tmp_path / "resume.ckpt", map_location="cpu", weights_only=False)

    assert stored["epoch"] == 1
    assert stored["callbacks"][first.state_key] == {BEST_LOSS_STATE: first.best_loss}
    assert not list(tmp_path.glob("*.partial"))

    second_writes: list[float] = []
    second = _export(tmp_path / "model.pt", second_writes)
    resumed = _restorer_trainer(tmp_path, max_epochs=3, export=second)
    resumed.fit(
        module,
        train_dataloaders=pair_loader,
        val_dataloaders=pair_loader,
        ckpt_path=str(tmp_path / "resume.ckpt"),
    )

    assert resumed.current_epoch == 3
    assert second.best_loss <= first.best_loss
    assert all(loss < first.best_loss for loss in second_writes)
