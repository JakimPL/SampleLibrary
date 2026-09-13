from __future__ import annotations

from lightning.pytorch import seed_everything

from samplemorph.training.analysis_data import AnalysisCorpus, AnalysisDataModule
from samplemorph.training.derived_examples import ExampleFamily
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import RESTORER_MONITORED_METRIC
from samplemorph.training.restorer_dataset import RestorerBatchItem, RestorerExample, crop_item, restorer_example
from samplemorph.training.restorer_export import RestorerWriter
from samplemorph.training.restorer_module import RestorerTrainingModule
from samplemorph.training.runs import RunPlacement, TrainingOutcome, fit_and_export, geometry_parameters
from samplemorph.training.settings import AnalysisTrainingSettings
from samplemorph.vocoders.pghi import gaussian_log_frequency
from samplemorph.vocoders.restored import restorer_path
from samplemorph.vocoders.restorer_model import RestorerShape


def run_restorer_training(
    corpus: AnalysisCorpus,
    *,
    settings: AnalysisTrainingSettings,
    placement: RunPlacement,
) -> TrainingOutcome:
    """Teach a restorer, writing what it learns as it learns it.

    What the run was asked to do reaches the record before the first epoch, so a pass that ends
    badly is still identifiable by the settings it ran under.

    Raises:
        ValueError: the corpus is canonicalized on an axis the restored vocoder does not read.
    """
    gaussian_log_frequency(corpus.canonicalizer.geometry)
    seed_everything(settings.run.random_seed, workers=True)
    placement.tracker.log_parameters(
        settings.as_parameters()
        | {"canonicalizer": corpus.canonicalizer_name}
        | geometry_parameters(corpus.canonicalizer.geometry)
    )

    data: AnalysisDataModule[RestorerExample, RestorerBatchItem] = AnalysisDataModule(
        corpus,
        family=ExampleFamily(derive=restorer_example, crop=crop_item, crop_frames=settings.crop_frames),
        run=settings.run,
    )
    module = RestorerTrainingModule(RestorerShape(channels=settings.channels), learning_rate=settings.run.learning_rate)
    path = restorer_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=RESTORER_MONITORED_METRIC,
        tracker=placement.tracker,
        writer=RestorerWriter(module, path, corpus, data.training_sample_count),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
