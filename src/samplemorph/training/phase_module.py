from __future__ import annotations

import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor

from samplemorph.training.metrics import (
    TRAINING_LOSS,
    VALIDATION_GRADIENT,
    VALIDATION_LOSS,
    VALIDATION_SPECTRAL,
)
from samplemorph.training.optimizers import cosine_optimizer
from samplemorph.training.phase_losses import AnalysisWindow, FrameAnalysis, LossParts, LossWeights, phase_loss
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
        analysis: FrameAnalysis,
        learning_rate: float,
        weights: LossWeights,
    ) -> None:
        super().__init__()
        self.model = PhaseModel(shape)
        self._fft_length = analysis.fft_length
        self._hop_length = analysis.hop_length
        self._learning_rate = learning_rate
        self._weights = weights
        self.register_buffer("taper", torch.as_tensor(analysis.taper, dtype=torch.float32))

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
        return cosine_optimizer(
            self.parameters(),
            learning_rate=self._learning_rate,
            total_steps=int(self.trainer.estimated_stepping_batches),
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
