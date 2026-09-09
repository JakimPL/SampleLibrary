from __future__ import annotations

from samplemorph.codecs.conditioned import codec_path
from samplemorph.codecs.conditioned_model import ConditionedCodecShape
from samplemorph.training.codec_data import CodecCorpus, CodecDataModule
from samplemorph.training.codec_export import CodecWriter
from samplemorph.training.codec_module import CodecTrainingModule
from samplemorph.training.codec_settings import CodecTrainingSettings
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import CODEC_MONITORED_METRIC
from samplemorph.training.runs import RunPlacement, TrainingOutcome, begin_cached_run, fit_and_export


def run_codec_training(
    corpus: CodecCorpus, *, settings: CodecTrainingSettings, placement: RunPlacement
) -> TrainingOutcome:
    """Teach a conditioned codec over a cached corpus, writing what it learns as it learns it."""
    begin_cached_run(
        placement,
        settings=settings.run,
        parameters=settings.as_parameters() | {"descriptor": corpus.descriptor_name},
        cache=corpus.cache,
    )
    data = CodecDataModule(corpus, settings=settings)
    module = CodecTrainingModule(
        ConditionedCodecShape(
            band_count=corpus.cache.description.band_count,
            time_columns=corpus.cache.description.time_columns,
            descriptor_size=corpus.descriptor.size,
            residual_size=settings.residual_size,
            width=settings.width,
        ),
        descriptor=corpus.descriptor.model,
        learning_rate=settings.run.learning_rate,
        weights=settings.weights,
        prior_warmup_steps=settings.prior_warmup_steps,
    )
    path = codec_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=CODEC_MONITORED_METRIC,
        tracker=placement.tracker,
        writer=CodecWriter(module, path, corpus, data.training_sample_count, settings.run.random_seed),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
