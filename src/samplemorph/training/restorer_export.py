from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from samplemorph.training.analysis_data import AnalysisCorpus
from samplemorph.training.export import ExportRecord
from samplemorph.training.metrics import RESTORER_VALIDATION_LEAST_SQUARES
from samplemorph.training.restorer_module import RestorerTrainingModule
from samplemorph.vocoders.pghi import gaussian_log_frequency
from samplemorph.vocoders.restored import RestorerDescription, save_restorer
from samplemorph.vocoders.restorer_model import Restorer


def describe_restorer(
    model: Restorer,
    *,
    corpus: AnalysisCorpus,
    record: ExportRecord,
    trained_sample_count: int,
    least_squares_validation_loss: float,
) -> RestorerDescription:
    """Everything needed to rebuild this network and to say where it came from.

    The geometry it was taught on travels whole, so a vocoder can tell a spectrogram from another
    grid apart from one this restorer reads; the least-squares number beside the best loss says
    how much of the grid's smoothing the run put back.
    """
    return RestorerDescription(
        canonicalizer=corpus.canonicalizer_name,
        geometry=gaussian_log_frequency(corpus.canonicalizer.geometry),
        channels=model.shape.channels,
        kernel_size=model.shape.kernel_size,
        dilations=model.shape.dilations,
        epochs=record.epochs,
        trained_sample_count=trained_sample_count,
        best_validation_loss=record.best_validation_loss,
        least_squares_validation_loss=least_squares_validation_loss,
    )


@dataclass(frozen=True)
class RestorerWriter:
    """Writes the weights a vocoder reads: the network and the description that rebuilds it.

    The module is held rather than taken from the trainer, so the weights written are known to be
    the ones this writer was built for; the least-squares baseline is read from the metrics the
    validation pass that triggered the write has just logged.
    """

    module: RestorerTrainingModule
    path: Path
    corpus: AnalysisCorpus
    trained_sample_count: int

    def __call__(self, record: ExportRecord) -> None:
        save_restorer(
            self.path,
            self.module.model,
            describe_restorer(
                self.module.model,
                corpus=self.corpus,
                record=record,
                trained_sample_count=self.trained_sample_count,
                least_squares_validation_loss=float(
                    self.module.trainer.callback_metrics[RESTORER_VALIDATION_LEAST_SQUARES]
                ),
            ),
        )
