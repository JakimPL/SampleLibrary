from __future__ import annotations

from samplemorph.features.shape import FeatureShape
from samplemorph.model_paths import features_path
from samplemorph.training.export import BestEpochExport
from samplemorph.training.features.data import FeatureCorpus, FeatureDataModule
from samplemorph.training.features.export import FeatureWriter
from samplemorph.training.features.module import FeatureTrainingModule
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.metrics import FEATURE_MONITORED_METRIC
from samplemorph.training.runs import RunPlacement, TrainingOutcome, begin_cached_run, fit_and_export


def run_feature_training(
    corpus: FeatureCorpus, *, settings: FeatureTrainingSettings, placement: RunPlacement
) -> TrainingOutcome:
    """Teach a feature autoencoder and its critic over a cached corpus, writing both as the reconstruction improves.

    The best epoch is the one that reconstructs the held-out sounds best, which means the same
    thing whatever the critic weight, so two runs that differ in the weight alone export comparable
    epochs.
    """
    data = FeatureDataModule(corpus, settings=settings)
    begin_cached_run(
        placement,
        settings=settings.run,
        parameters=settings.as_parameters()
        | {
            "training_sample_count": str(len(corpus.training_positions)),
            "validation_sample_count": str(len(corpus.validation_positions)),
        },
        cache=corpus.cache,
    )
    description = corpus.cache.description
    module = FeatureTrainingModule(
        FeatureShape(
            band_count=description.band_count,
            time_columns=description.time_columns,
            latent_size=settings.latent_size,
            width=settings.width,
        ),
        settings=settings,
        dynamic_range_db=description.geometry.dynamic_range_db,
    )
    path = features_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=FEATURE_MONITORED_METRIC,
        tracker=placement.tracker,
        writer=FeatureWriter(module=module, path=path, corpus=corpus, settings=settings),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
