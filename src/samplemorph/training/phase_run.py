from __future__ import annotations

from lightning.pytorch import seed_everything

from samplemorph.geometry import fourier_bin_count
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import MONITORED_METRIC
from samplemorph.training.phase_data import PhaseCorpus, PhaseDataModule
from samplemorph.training.phase_export import PhaseModelWriter
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.training.runs import RunPlacement, TrainingOutcome, fit_and_export
from samplemorph.training.settings import PhaseTrainingSettings
from samplemorph.vocoders.learned import phase_model_path
from samplemorph.vocoders.phase_model import PhaseModelShape


def run_phase_training(
    corpus: PhaseCorpus,
    *,
    settings: PhaseTrainingSettings,
    placement: RunPlacement,
) -> TrainingOutcome:
    """Teach a phase model, writing what it learns as it learns it.

    What the run was asked to do reaches the record before the first epoch, so a pass that ends
    badly is still identifiable by the settings it ran under.
    """
    seed_everything(settings.run.random_seed, workers=True)
    placement.tracker.log_parameters(settings.as_parameters() | {"canonicalizer": corpus.canonicalizer_name})
    geometry = corpus.canonicalizer.geometry
    data = PhaseDataModule(
        corpus,
        batch_size=settings.run.batch_size,
        crop_frames=settings.crop_frames,
        worker_count=settings.run.worker_count,
        random_seed=settings.run.random_seed,
    )
    module = PhaseTrainingModule(
        PhaseModelShape(bin_count=fourier_bin_count(fft_length=geometry.fft_length), channels=settings.channels),
        fft_length=geometry.fft_length,
        hop_length=geometry.hop_length,
        learning_rate=settings.run.learning_rate,
        weights=settings.weights,
    )
    path = phase_model_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=MONITORED_METRIC,
        tracker=placement.tracker,
        writer=PhaseModelWriter(module, path, corpus, data.training_sample_count),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
