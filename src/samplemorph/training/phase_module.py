from __future__ import annotations

import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import LRSchedulerConfigType, OptimizerLRSchedulerConfig
from torch import Tensor

from samplemorph.training.metrics import (
    TRAINING_LOSS,
    VALIDATION_GRADIENT,
    VALIDATION_LOSS,
    VALIDATION_SPECTRAL,
)
from samplemorph.training.phase_losses import AnalysisWindow, LossParts, LossWeights, phase_loss
from samplemorph.vocoders.phase_model import PhaseModel, PhaseModelShape

PhaseBatch = tuple[Tensor, Tensor, Tensor, Tensor]


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class PhaseTrainingModule(LightningModule):
    """Teaches a `PhaseModel` the phase that belongs with the magnitudes this pipeline produces.

    The network itself stays an ordinary module, held here rather than inherited from, so what a
    run produces is loadable by a vocoder that knows nothing about how it was trained.

    The analysis taper is registered as a buffer, which is what moves it to whichever device the
    step runs on and carries it into a checkpoint alongside the weights.
    """

    taper: Tensor

    def __init__(
        self,
        shape: PhaseModelShape,
        *,
        fft_length: int,
        hop_length: int,
        learning_rate: float,
        weights: LossWeights,
    ) -> None:
        super().__init__()
        self.model = PhaseModel(shape)
        self._fft_length = fft_length
        self._hop_length = hop_length
        self._learning_rate = learning_rate
        self._weights = weights
        self.register_buffer("taper", torch.hann_window(fft_length))

    def forward(self, magnitude: Tensor, *, frame_offset: Tensor | None = None) -> Tensor:
        phase: Tensor = self.model(magnitude, frame_offset=frame_offset)
        return phase

    def training_step(self, batch: PhaseBatch, _batch_index: int) -> Tensor:
        parts = self._loss_parts(batch)
        self.log(TRAINING_LOSS, parts.total, on_step=True, on_epoch=True, prog_bar=True)
        return parts.total

    def validation_step(self, batch: PhaseBatch, _batch_index: int) -> Tensor:
        parts = self._loss_parts(batch)
        self.log(VALIDATION_LOSS, parts.total, on_epoch=True, prog_bar=True)
        self.log(VALIDATION_GRADIENT, parts.gradient, on_epoch=True)
        self.log(VALIDATION_SPECTRAL, parts.spectral, on_epoch=True)
        return parts.total

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        """The optimizer, and a rate that falls over the whole run rather than over each epoch.

        The schedule is told how many steps the run will take, so a rate reaching its floor at the
        end holds whatever the corpus size and batch size work out to.
        """
        optimizer = torch.optim.AdamW(self.parameters(), lr=self._learning_rate)
        schedule = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=max(int(self.trainer.estimated_stepping_batches), 1)
        )
        return OptimizerLRSchedulerConfig(
            optimizer=optimizer, lr_scheduler=LRSchedulerConfigType(scheduler=schedule, interval="step")
        )

    def _loss_parts(self, batch: PhaseBatch) -> LossParts:
        magnitude, cosine, sine, frame_offset = batch
        return phase_loss(
            self.model(magnitude, frame_offset=frame_offset),
            torch.stack((cosine, sine), dim=1),
            magnitude,
            window=AnalysisWindow(fft_length=self._fft_length, hop_length=self._hop_length, taper=self.taper),
            weights=self._weights,
        )
