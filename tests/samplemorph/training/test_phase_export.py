from __future__ import annotations

from pathlib import Path

import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.phase_data import PhaseCorpus
from samplemorph.training.phase_dataset import PhaseBatchItem
from samplemorph.training.phase_export import PhaseExport, describe_phase_model
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.vocoders.learned import load_phase_model
from tests.samplemorph.training.conftest import CHANNELS

CANONICALIZER_NAME = "log_frequency"
TRAINED_SAMPLE_COUNT = 4


def _corpus(library_root: Path) -> PhaseCorpus:
    return PhaseCorpus(
        samples=(),
        library_root=library_root,
        canonicalizer=CANONICALIZER_REGISTRY[CANONICALIZER_NAME](),
        canonicalizer_name=CANONICALIZER_NAME,
    )


def _export(module: PhaseTrainingModule, path: Path) -> PhaseExport:
    return PhaseExport(
        module,
        path=path,
        corpus=_corpus(path.parent),
        trained_sample_count=TRAINED_SAMPLE_COUNT,
    )


def test_a_description_carries_what_rebuilding_the_network_needs(
    tmp_path: Path, phase_module: PhaseTrainingModule
) -> None:
    description = describe_phase_model(
        phase_module.model,
        corpus=_corpus(tmp_path),
        epochs=1,
        trained_sample_count=TRAINED_SAMPLE_COUNT,
        best_validation_loss=1.5,
    )

    assert description.channels == CHANNELS
    assert description.canonicalizer == CANONICALIZER_NAME


def test_an_exported_run_is_read_back_as_the_network_it_trained(
    tmp_path: Path,
    phase_module: PhaseTrainingModule,
    crop_loader: DataLoader[PhaseBatchItem],
    fast_trainer: Trainer,
) -> None:
    """The export is the run's deliverable, so a vocoder must read it with no trainer involved."""
    path = tmp_path / "phase.pt"
    export = _export(phase_module, path)
    fast_trainer.fit(phase_module, train_dataloaders=crop_loader, val_dataloaders=crop_loader)

    export.on_validation_end(fast_trainer, phase_module)
    vocoder = load_phase_model(path, device=torch.device("cpu"))

    assert vocoder.description.channels == CHANNELS
    assert vocoder.description.trained_sample_count == TRAINED_SAMPLE_COUNT


def test_an_epoch_that_beats_no_earlier_one_leaves_the_export_alone(
    tmp_path: Path,
    phase_module: PhaseTrainingModule,
    crop_loader: DataLoader[PhaseBatchItem],
    fast_trainer: Trainer,
) -> None:
    path = tmp_path / "phase.pt"
    export = _export(phase_module, path)
    fast_trainer.fit(phase_module, train_dataloaders=crop_loader, val_dataloaders=crop_loader)
    export.on_validation_end(fast_trainer, phase_module)
    first_written = path.stat().st_mtime_ns

    export.on_validation_end(fast_trainer, phase_module)

    assert path.stat().st_mtime_ns == first_written
