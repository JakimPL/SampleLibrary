from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.descriptors.learned import DescriptorDescription, save_descriptor
from samplemorph.training.descriptor_data import DescriptorCorpus
from samplemorph.training.descriptor_module import DescriptorTrainingModule


def describe_descriptor(
    module: DescriptorTrainingModule,
    *,
    corpus: DescriptorCorpus,
    epochs: int,
    trained_sample_count: int,
    best_validation_loss: float,
) -> DescriptorDescription:
    """Everything needed to rebuild this network and to say where it came from."""
    cache = corpus.cache.description
    return DescriptorDescription(
        canonicalizer=cache.canonicalizer,
        geometry=cache.geometry,
        bands_per_semitone=cache.bands_per_semitone,
        shape=module.model.shape,
        teacher_experiment_id=corpus.teacher_experiment_id,
        epochs=epochs,
        trained_sample_count=trained_sample_count,
        best_validation_loss=best_validation_loss,
    )


@dataclass(frozen=True)
class DescriptorWriter:
    """Writes the weights a descriptor reads: the network and the description that rebuilds it."""

    module: DescriptorTrainingModule
    path: Path
    corpus: DescriptorCorpus
    trained_sample_count: int

    def __call__(self, *, epochs: int, best_validation_loss: float) -> None:
        save_descriptor(
            self.path,
            self.module.model,
            describe_descriptor(
                self.module,
                corpus=self.corpus,
                epochs=epochs,
                trained_sample_count=self.trained_sample_count,
                best_validation_loss=best_validation_loss,
            ),
        )
