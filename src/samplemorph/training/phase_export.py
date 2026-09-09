from __future__ import annotations

from pathlib import Path

from lightning.pytorch import Callback, LightningModule, Trainer

from samplemorph.training.metrics import MONITORED_METRIC
from samplemorph.training.phase_data import PhaseCorpus
from samplemorph.training.phase_module import PhaseTrainingModule
from samplemorph.vocoders.learned import PhaseModelDescription, save_phase_model
from samplemorph.vocoders.phase_model import PhaseModel


def describe_phase_model(
    model: PhaseModel,
    *,
    corpus: PhaseCorpus,
    epochs: int,
    trained_sample_count: int,
    best_validation_loss: float,
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
        epochs=epochs,
        trained_sample_count=trained_sample_count,
        best_validation_loss=best_validation_loss,
    )


class PhaseExport(Callback):
    """Writes the weights a vocoder reads, each time an epoch beats every epoch before it.

    This is the run's deliverable rather than its resume point: the file holds the network and the
    description that rebuilds it, and nothing about the optimizer or the schedule. A run being
    listened to while it is still going reads this, and the trainer's own checkpoint carries what
    resuming needs.

    The module is held rather than taken from the call, so the weights written are known to be the
    ones this export was built for.
    """

    def __init__(
        self,
        module: PhaseTrainingModule,
        *,
        path: Path,
        corpus: PhaseCorpus,
        trained_sample_count: int,
    ) -> None:
        super().__init__()
        self._module = module
        self._path = path
        self._corpus = corpus
        self._trained_sample_count = trained_sample_count
        self._best_loss = float("inf")

    @property
    def best_loss(self) -> float:
        return self._best_loss

    @property
    def path(self) -> Path:
        return self._path

    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        if trainer.sanity_checking:
            return

        reached = trainer.callback_metrics.get(MONITORED_METRIC)
        if reached is None or float(reached) >= self._best_loss:
            return

        self._best_loss = float(reached)
        save_phase_model(
            self._path,
            self._module.model,
            describe_phase_model(
                self._module.model,
                corpus=self._corpus,
                epochs=trainer.current_epoch + 1,
                trained_sample_count=self._trained_sample_count,
                best_validation_loss=self._best_loss,
            ),
        )
