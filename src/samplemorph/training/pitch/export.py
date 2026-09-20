from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.coordinates.pitch_head.store import (
    NO_CALIBRATION_SEMITONES,
    PitchHeadDescription,
    save_pitch_head,
)
from samplemorph.training.export import ExportRecord
from samplemorph.training.pitch.data import PitchCorpus
from samplemorph.training.pitch.module import PitchTrainingModule
from samplemorph.training.pitch.settings import PitchTrainingSettings


def describe_pitch_head(
    module: PitchTrainingModule,
    *,
    name: str,
    corpus: PitchCorpus,
    settings: PitchTrainingSettings,
    record: ExportRecord,
) -> PitchHeadDescription:
    """Everything needed to rebuild the head, to say how it was taught, and to read it on unseen sounds.

    The calibration is read from known tones once the run is over, so an epoch exported while the
    run is still going reads in its own bins until then.
    """
    return PitchHeadDescription(
        name=name,
        cache=corpus.cache.directory.name,
        analysis=corpus.cache.description.analysis,
        shape=module.network.shape,
        calibration_semitones=NO_CALIBRATION_SEMITONES,
        trusted_reliability=settings.trusted_reliability,
        random_seed=settings.run.random_seed,
        epochs=record.epochs,
        trained_sample_count=len(corpus.training_positions),
        best_validation_error=record.best_validation_loss,
        validation_hashes=corpus.validation_hashes,
        parameters=settings.as_parameters(),
    )


@dataclass(frozen=True)
class PitchHeadWriter:
    """Writes a pitch head: its network, and the description that rebuilds it."""

    module: PitchTrainingModule
    path: Path
    corpus: PitchCorpus
    settings: PitchTrainingSettings

    def __call__(self, record: ExportRecord) -> None:
        save_pitch_head(
            self.path,
            network=self.module.network,
            description=describe_pitch_head(
                self.module, name=self.path.stem, corpus=self.corpus, settings=self.settings, record=record
            ),
        )
