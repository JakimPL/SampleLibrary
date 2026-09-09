from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.codecs.conditioned import ConditionedCodecDescription, save_conditioned_codec
from samplemorph.training.codec_data import CodecCorpus
from samplemorph.training.codec_module import CodecTrainingModule
from samplemorph.training.export import ExportRecord


def describe_codec(
    module: CodecTrainingModule,
    *,
    corpus: CodecCorpus,
    record: ExportRecord,
    trained_sample_count: int,
    random_seed: int,
) -> ConditionedCodecDescription:
    """Everything needed to rebuild this network and to say where it came from."""
    return ConditionedCodecDescription(
        canonicalizer=corpus.cache.description.canonicalizer,
        geometry=corpus.cache.description.geometry,
        shape=module.model.shape,
        descriptor=corpus.descriptor_name,
        epochs=record.epochs,
        trained_sample_count=trained_sample_count,
        random_seed=random_seed,
        best_validation_loss=record.best_validation_loss,
    )


@dataclass(frozen=True)
class CodecWriter:
    """Writes the weights a codec reads: the network and the description that rebuilds it."""

    module: CodecTrainingModule
    path: Path
    corpus: CodecCorpus
    trained_sample_count: int
    random_seed: int

    def __call__(self, record: ExportRecord) -> None:
        save_conditioned_codec(
            self.path,
            self.module.model,
            describe_codec(
                self.module,
                corpus=self.corpus,
                record=record,
                trained_sample_count=self.trained_sample_count,
                random_seed=self.random_seed,
            ),
        )
