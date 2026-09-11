from __future__ import annotations

from lightning.pytorch import seed_everything

from samplemorph.geometry import analysis_taper, fourier_bin_count
from samplemorph.training.analysis_data import AnalysisCorpus, AnalysisDataModule
from samplemorph.training.derived_examples import ExampleFamily
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import MONITORED_METRIC
from samplemorph.training.phase_dataset import PhaseBatchItem, PhaseExample, crop_item, phase_example
from samplemorph.training.phase_export import PhaseModelWriter
from samplemorph.training.phase_losses import FrameAnalysis, LossWeights
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.training.runs import RunPlacement, TrainingOutcome, fit_and_export
from samplemorph.training.settings import AnalysisTrainingSettings
from samplemorph.vocoders.learned import phase_model_path
from samplemorph.vocoders.phase_model import PhaseModelShape


def run_phase_training(
    corpus: AnalysisCorpus,
    *,
    settings: AnalysisTrainingSettings,
    weights: LossWeights,
    placement: RunPlacement,
) -> TrainingOutcome:
    """Teach a phase model, writing what it learns as it learns it.

    What the run was asked to do reaches the record before the first epoch, so a pass that ends
    badly is still identifiable by the settings it ran under.
    """
    seed_everything(settings.run.random_seed, workers=True)
    placement.tracker.log_parameters(
        settings.as_parameters()
        | {
            "canonicalizer": corpus.canonicalizer_name,
            "gradient_weight": str(weights.gradient),
            "spectral_weight": str(weights.spectral),
        }
    )
    geometry = corpus.canonicalizer.geometry

    data: AnalysisDataModule[PhaseExample, PhaseBatchItem] = AnalysisDataModule(
        corpus,
        family=ExampleFamily(derive=phase_example, crop=crop_item, crop_frames=settings.crop_frames),
        run=settings.run,
    )
    module = PhaseTrainingModule(
        PhaseModelShape(bin_count=fourier_bin_count(fft_length=geometry.fft_length), channels=settings.channels),
        analysis=FrameAnalysis(
            fft_length=geometry.fft_length, hop_length=geometry.hop_length, taper=analysis_taper(geometry)
        ),
        learning_rate=settings.run.learning_rate,
        weights=weights,
    )
    path = phase_model_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=MONITORED_METRIC,
        tracker=placement.tracker,
        writer=PhaseModelWriter(module, path, corpus, data.training_sample_count),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
