from __future__ import annotations

from pathlib import Path

import pytest
import torch
from lightning.pytorch import Trainer
from torch.utils.data import DataLoader

from samplecore.tracking.silent import SilentRun
from samplemorph.geometry import AnalysisWindow, log_frequency_geometry
from samplemorph.registries import CANONICALIZER_REGISTRY, canonicalizer_for_geometry
from samplemorph.training.analysis_data import AnalysisCorpus
from samplemorph.training.export import BestEpochExport, ExportRecord
from samplemorph.training.metrics import RESTORER_MONITORED_METRIC
from samplemorph.training.restorer_dataset import RestorerBatchItem
from samplemorph.training.restorer_export import RestorerWriter, describe_restorer
from samplemorph.training.restorer_module import RestorerTrainingModule
from samplemorph.vocoders.restored import load_restorer
from tests.samplemorph.training.conftest import RESTORER_CHANNELS

CANONICALIZER_NAME = "log_frequency"
TRAINED_SAMPLE_COUNT = 4


def _corpus(library_root: Path) -> AnalysisCorpus:
    return AnalysisCorpus(
        samples=(),
        library_root=library_root,
        canonicalizer=CANONICALIZER_REGISTRY[CANONICALIZER_NAME](),
        canonicalizer_name=CANONICALIZER_NAME,
    )


def test_a_description_carries_the_geometry_and_the_baseline_beside_the_loss(
    tmp_path: Path, restorer_module: RestorerTrainingModule
) -> None:
    corpus = _corpus(tmp_path)

    description = describe_restorer(
        restorer_module.model,
        corpus=corpus,
        record=ExportRecord(epochs=2, best_validation_loss=0.05),
        trained_sample_count=TRAINED_SAMPLE_COUNT,
        least_squares_validation_loss=0.08,
    )

    assert description.channels == RESTORER_CHANNELS
    assert description.geometry == corpus.canonicalizer.geometry
    assert description.epochs == 2
    assert description.best_validation_loss < description.least_squares_validation_loss


def test_a_corpus_on_another_analysis_is_refused_by_name(
    tmp_path: Path, restorer_module: RestorerTrainingModule
) -> None:
    hann = canonicalizer_for_geometry(log_frequency_geometry(analysis_window=AnalysisWindow.HANN))
    corpus = AnalysisCorpus(
        samples=(), library_root=tmp_path, canonicalizer=hann, canonicalizer_name=CANONICALIZER_NAME
    )

    with pytest.raises(ValueError, match="hann taper"):
        describe_restorer(
            restorer_module.model,
            corpus=corpus,
            record=ExportRecord(epochs=1, best_validation_loss=0.05),
            trained_sample_count=TRAINED_SAMPLE_COUNT,
            least_squares_validation_loss=0.08,
        )


def test_an_exported_run_is_read_back_as_the_vocoder_it_trained(
    tmp_path: Path,
    restorer_module: RestorerTrainingModule,
    pair_loader: DataLoader[RestorerBatchItem],
    fast_trainer: Trainer,
) -> None:
    """The export is the run's deliverable, so a vocoder must read it with no trainer involved."""
    path = tmp_path / "restorer.pt"
    export = BestEpochExport(
        path=path,
        monitored=RESTORER_MONITORED_METRIC,
        tracker=SilentRun(),
        writer=RestorerWriter(restorer_module, path, _corpus(tmp_path), TRAINED_SAMPLE_COUNT),
    )
    fast_trainer.fit(restorer_module, train_dataloaders=pair_loader, val_dataloaders=pair_loader)

    export.on_validation_end(fast_trainer, restorer_module)
    vocoder = load_restorer(path, device=torch.device("cpu"))

    assert vocoder.description.channels == RESTORER_CHANNELS
    assert vocoder.description.trained_sample_count == TRAINED_SAMPLE_COUNT
    assert vocoder.description.least_squares_validation_loss > 0.0
