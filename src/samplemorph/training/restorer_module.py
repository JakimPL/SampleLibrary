from __future__ import annotations

from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor

from samplemorph.training.metrics import (
    RESTORER_TRAINING_LOSS,
    RESTORER_VALIDATION_COARSE,
    RESTORER_VALIDATION_FINE,
    RESTORER_VALIDATION_LEAST_SQUARES,
    RESTORER_VALIDATION_LOSS,
)
from samplemorph.training.optimizers import scheduled_over_the_run
from samplemorph.training.restorer_losses import RestorerLossParts, restorer_loss
from samplemorph.vocoders.restorer_model import Restorer
from samplemorph.vocoders.restorer_shape import RestorerShape

RestorerBatch = tuple[Tensor, Tensor]


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class RestorerTrainingModule(LightningModule):
    """Teaches a `Restorer` the fine structure the grid removes from this pipeline's magnitudes.

    The network itself stays an ordinary module, held here rather than inherited from, so what a
    run produces is loadable by a vocoder that knows nothing about how it was trained. Beside its
    own loss the validation pass reads the least-squares reading's distance from the clean
    analysis, which is the loss of leaving the magnitude alone: an epoch is only an improvement
    where it sits under that number.
    """

    def __init__(self, shape: RestorerShape, *, learning_rate: float) -> None:
        super().__init__()
        self.model = Restorer(shape)
        self._learning_rate = learning_rate

    def forward(self, decibels: Tensor) -> Tensor:
        restored: Tensor = self.model(decibels)
        return restored

    def training_step(self, batch: RestorerBatch, _batch_index: int) -> Tensor:
        parts = self._loss_parts(batch)
        self.log(RESTORER_TRAINING_LOSS, parts.total, on_step=True, on_epoch=True, prog_bar=True)
        return parts.total

    def validation_step(self, batch: RestorerBatch, _batch_index: int) -> Tensor:
        least_squares, clean = batch
        parts = self._loss_parts(batch)
        self.log(RESTORER_VALIDATION_LOSS, parts.total, on_epoch=True, prog_bar=True)
        self.log(RESTORER_VALIDATION_FINE, parts.fine, on_epoch=True)
        self.log(RESTORER_VALIDATION_COARSE, parts.coarse, on_epoch=True)
        self.log(RESTORER_VALIDATION_LEAST_SQUARES, restorer_loss(least_squares, clean).total, on_epoch=True)
        return parts.total

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        return scheduled_over_the_run(self, self.parameters(), learning_rate=self._learning_rate)

    def _loss_parts(self, batch: RestorerBatch) -> RestorerLossParts:
        least_squares, clean = batch
        return restorer_loss(self.model(least_squares).float(), clean)
