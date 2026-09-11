from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.training.analysis_data import AnalysisCorpus
from samplemorph.training.export import ExportRecord
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.vocoders.learned import PhaseModelDescription, save_phase_model
from samplemorph.vocoders.phase_model import PhaseModel


def describe_phase_model(
    model: PhaseModel,
    *,
    corpus: AnalysisCorpus,
    record: ExportRecord,
    trained_sample_count: int,
) -> PhaseModelDescription:
    """Everything needed to rebuild this network and to say where it came from.

    The axis it was taught on carries its own analysis window, so the corpus answers both what the
    model was trained against and how a vocoder must read for it.
    """
    geometry = corpus.canonicalizer.geometry
    return PhaseModelDescription(
        canonicalizer=corpus.canonicalizer_name,
        bin_count=model.shape.bin_count,
        frames_per_turn=model.shape.frames_per_turn,
        channels=model.shape.channels,
        kernel_size=model.shape.kernel_size,
        dilations=model.shape.dilations,
        fft_length=geometry.fft_length,
        hop_length=geometry.hop_length,
        epochs=record.epochs,
        trained_sample_count=trained_sample_count,
        best_validation_loss=record.best_validation_loss,
    )


@dataclass(frozen=True)
class PhaseModelWriter:
    """Writes the weights a vocoder reads: the network and the description that rebuilds it.

    The module is held rather than taken from the trainer, so the weights written are known to be
    the ones this writer was built for.
    """

    module: PhaseTrainingModule
    path: Path
    corpus: AnalysisCorpus
    trained_sample_count: int

    def __call__(self, record: ExportRecord) -> None:
        save_phase_model(
            self.path,
            self.module.model,
            describe_phase_model(
                self.module.model,
                corpus=self.corpus,
                record=record,
                trained_sample_count=self.trained_sample_count,
            ),
        )
