from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.features.store import FeatureDescription, save_features
from samplemorph.training.export import ExportRecord
from samplemorph.training.features.data import FeatureCorpus
from samplemorph.training.features.module import FeatureTrainingModule
from samplemorph.training.features.settings import FeatureTrainingSettings


def describe_features(
    module: FeatureTrainingModule, *, corpus: FeatureCorpus, settings: FeatureTrainingSettings, record: ExportRecord
) -> FeatureDescription:
    """Everything needed to rebuild both networks, to say how they were taught, and to read them on unseen sounds."""
    cache = corpus.cache.description
    return FeatureDescription(
        cache=corpus.cache.directory.name,
        canonicalizer=cache.canonicalizer,
        geometry=cache.geometry,
        bands_per_semitone=cache.bands_per_semitone,
        shape=module.autoencoder.shape,
        critic_weight=settings.critic_weight,
        critic_mix=settings.critic_mix,
        random_seed=settings.run.random_seed,
        epochs=record.epochs,
        trained_sample_count=len(corpus.training_positions),
        best_validation_loss=record.best_validation_loss,
        validation_hashes=corpus.validation_hashes,
    )


@dataclass(frozen=True)
class FeatureWriter:
    """Writes a feature model: the autoencoder, its critic, and the description that rebuilds them."""

    module: FeatureTrainingModule
    path: Path
    corpus: FeatureCorpus
    settings: FeatureTrainingSettings

    def __call__(self, record: ExportRecord) -> None:
        save_features(
            self.path,
            autoencoder=self.module.autoencoder,
            critic=self.module.critic,
            description=describe_features(self.module, corpus=self.corpus, settings=self.settings, record=record),
        )
