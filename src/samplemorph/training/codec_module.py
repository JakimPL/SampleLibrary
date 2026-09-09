from __future__ import annotations

import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor, nn

from samplemorph.codecs.conditioned_model import ConditionedCodecModel, ConditionedCodecShape
from samplemorph.descriptors.grid_descriptor import GridDescriptor
from samplemorph.training.codec_losses import CodecLossParts, CodecLossWeights, CodecPrediction, codec_loss
from samplemorph.training.metrics import (
    CODEC_TRAINING_CYCLE,
    CODEC_TRAINING_LOSS,
    CODEC_TRAINING_PRIOR,
    CODEC_TRAINING_RECONSTRUCTION,
    CODEC_VALIDATION_CYCLE,
    CODEC_VALIDATION_LOSS,
    CODEC_VALIDATION_PRIOR,
    CODEC_VALIDATION_RECONSTRUCTION,
)
from samplemorph.training.optimizers import cosine_optimizer

# (positions, grids, canonical durations)
CodecBatch = tuple[Tensor, Tensor, Tensor]


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class CodecTrainingModule(LightningModule):
    """Teaches a `ConditionedCodecModel` to rebuild a grid from a residual beside its descriptor.

    The descriptor network rides along frozen: it reads each grid's pooled form to say what the
    sound is, which the codec is conditioned on, and reads the decoded grid the same way for the
    cycle term. Its weights stay out of the optimizer and out of the checkpoint.
    """

    def __init__(
        self,
        shape: ConditionedCodecShape,
        *,
        descriptor: GridDescriptor,
        learning_rate: float,
        weights: CodecLossWeights,
        prior_warmup_steps: int,
    ) -> None:
        super().__init__()
        self.model = ConditionedCodecModel(shape)
        self.descriptor = descriptor.eval()
        for parameter in self.descriptor.parameters():
            parameter.requires_grad_(False)
        self._learning_rate = learning_rate
        self._weights = weights
        self._prior_warmup_steps = prior_warmup_steps

    def describe(self, grid: Tensor, duration: Tensor) -> Tensor:
        """What the descriptor says about a grid, read at the resolution it was taught on."""
        # pylint: disable-next=not-callable
        pooled = nn.functional.adaptive_avg_pool1d(grid.transpose(1, 2), self.descriptor.shape.band_count)
        described: Tensor = self.descriptor(pooled.transpose(1, 2), duration)
        return described

    def training_step(self, batch: CodecBatch, _batch_index: int) -> Tensor:
        parts = self._loss_parts(batch, prior_share=self._prior_share())
        self.log(CODEC_TRAINING_LOSS, parts.total, on_step=True, on_epoch=True, prog_bar=True)
        self.log(CODEC_TRAINING_RECONSTRUCTION, parts.reconstruction, on_step=False, on_epoch=True)
        self.log(CODEC_TRAINING_PRIOR, parts.prior, on_step=False, on_epoch=True)
        self.log(CODEC_TRAINING_CYCLE, parts.cycle, on_step=False, on_epoch=True)
        return parts.total

    def validation_step(self, batch: CodecBatch, _batch_index: int) -> Tensor:
        """Judged at the prior's full weight whatever the warm-up has reached, so epochs compare."""
        parts = self._loss_parts(batch, prior_share=1.0)
        self.log(CODEC_VALIDATION_LOSS, parts.total, on_epoch=True, prog_bar=True)
        self.log(CODEC_VALIDATION_RECONSTRUCTION, parts.reconstruction, on_epoch=True)
        self.log(CODEC_VALIDATION_PRIOR, parts.prior, on_epoch=True)
        self.log(CODEC_VALIDATION_CYCLE, parts.cycle, on_epoch=True)
        return parts.total

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        return cosine_optimizer(
            self.model.parameters(),
            learning_rate=self._learning_rate,
            total_steps=int(self.trainer.estimated_stepping_batches),
        )

    def _prior_share(self) -> float:
        if self._prior_warmup_steps == 0:
            return 1.0
        return min(float(self.global_step) / self._prior_warmup_steps, 1.0)

    def _loss_parts(self, batch: CodecBatch, *, prior_share: float) -> CodecLossParts:
        _positions, grid, duration = batch
        with torch.no_grad():
            descriptor = self.describe(grid, duration)
        reconstruction, mean, log_variance = self.model(grid, descriptor)
        prediction = CodecPrediction(
            grid=reconstruction,
            mean=mean,
            log_variance=log_variance,
            described=self.describe(reconstruction, duration),
        )
        return codec_loss(
            prediction, target=grid, descriptor=descriptor, weights=self._weights, prior_share=prior_share
        )
