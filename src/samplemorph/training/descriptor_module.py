from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor

from samplecore.labeling.ranking import ndcg_per_query, nearest_first
from samplemorph.descriptors.descriptor_shape import DescriptorShape
from samplemorph.descriptors.grid_descriptor import GridDescriptor
from samplemorph.training.descriptor_data import NO_LABEL
from samplemorph.training.descriptor_losses import DescriptorLossParts, DescriptorTargets, descriptor_loss
from samplemorph.training.descriptor_settings import DescriptorLossWeights
from samplemorph.training.metrics import (
    DESCRIPTOR_TRAINING_DISTILLATION,
    DESCRIPTOR_TRAINING_LABELS,
    DESCRIPTOR_TRAINING_LOSS,
    DESCRIPTOR_TRAINING_RETUNING,
    DESCRIPTOR_VALIDATION_LOSS,
    DESCRIPTOR_VALIDATION_NDCG,
    DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE,
    DESCRIPTOR_VALIDATION_TEACHER_COSINE,
)
from samplemorph.training.optimizers import scheduled_over_the_run

# (positions, stored grids, retuned grids, stored durations, retuned durations)
DescriptorBatch = tuple[Tensor, Tensor, Tensor, Tensor, Tensor]
# The neighborhood the held-out labels are read over, matching the harness's own.
VALIDATION_NEIGHBORHOOD: Final[int] = 10


@dataclass(frozen=True)
class TeachingMaterial:
    """What every cached sample is taught against, row by row: the teacher's vector and the labels.

    `label_position` names each sample's row in `agreements` or `NO_LABEL`; `held_out` marks the
    labeled samples the run is judged on and never taught.
    """

    teacher: Tensor
    label_position: Tensor
    held_out: Tensor
    agreements: Tensor


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class DescriptorTrainingModule(LightningModule):
    """Teaches a `GridDescriptor` what the teacher hears, that a retuning changes nothing, and what the labels say.

    The network stays an ordinary module, held rather than inherited from, so what a run produces
    is loadable by a descriptor that knows nothing about how it was trained.

    What every sample is taught against -- its teacher vector, its label's row, and the agreement
    between labels -- lives on the device as buffers that stay out of the checkpoint, since they
    are the corpus's and are rebuilt from it; a batch then carries positions and the module looks
    the rest up.
    """

    teacher: Tensor
    label_position: Tensor
    held_out: Tensor
    agreements: Tensor

    def __init__(
        self,
        shape: DescriptorShape,
        *,
        learning_rate: float,
        weights: DescriptorLossWeights,
        material: TeachingMaterial,
    ) -> None:
        super().__init__()
        self.model = GridDescriptor(shape)
        self._learning_rate = learning_rate
        self._weights = weights
        self.register_buffer("teacher", material.teacher, persistent=False)
        self.register_buffer("label_position", material.label_position, persistent=False)
        self.register_buffer("held_out", material.held_out, persistent=False)
        self.register_buffer("agreements", material.agreements, persistent=False)
        self._validation_positions: list[Tensor] = []
        self._validation_stored: list[Tensor] = []
        self._validation_retuned: list[Tensor] = []

    def forward(self, grid: Tensor, duration: Tensor) -> Tensor:
        vectors: Tensor = self.model(grid, duration)
        return vectors

    def training_step(self, batch: DescriptorBatch, _batch_index: int) -> Tensor:
        parts = self._loss_parts(batch)
        self.log(DESCRIPTOR_TRAINING_LOSS, parts.total, on_step=True, on_epoch=True, prog_bar=True)
        self.log(DESCRIPTOR_TRAINING_DISTILLATION, parts.distillation, on_step=False, on_epoch=True)
        self.log(DESCRIPTOR_TRAINING_RETUNING, parts.retuning, on_step=False, on_epoch=True)
        self.log(DESCRIPTOR_TRAINING_LABELS, parts.labels, on_step=False, on_epoch=True)
        return parts.total

    def validation_step(self, batch: DescriptorBatch, _batch_index: int) -> Tensor:
        positions, stored_grid, retuned_grid, stored_duration, retuned_duration = batch
        stored = self(stored_grid, stored_duration)
        retuned = self(retuned_grid, retuned_duration)
        no_labels = DescriptorTargets(
            teacher=self.teacher[positions],
            labeled=torch.zeros(0, dtype=torch.long, device=stored.device),
            agreements=torch.zeros((0, 0), device=stored.device),
        )
        parts = descriptor_loss(stored, retuned, targets=no_labels, weights=self._weights)
        self.log(DESCRIPTOR_VALIDATION_LOSS, parts.total, on_epoch=True, prog_bar=True)
        self._validation_positions.append(positions)
        self._validation_stored.append(stored)
        self._validation_retuned.append(retuned)
        return parts.total

    def on_validation_epoch_end(self) -> None:
        """Read the whole validation set at once: the retuning check and the held-out labels need every row."""
        positions = torch.cat(self._validation_positions)
        stored = torch.cat(self._validation_stored)
        retuned = torch.cat(self._validation_retuned)
        self._validation_positions.clear()
        self._validation_stored.clear()
        self._validation_retuned.clear()
        self.log(DESCRIPTOR_VALIDATION_TEACHER_COSINE, (stored * self.teacher[positions]).sum(dim=-1).mean())
        self.log(DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE, _retune_rank_one(stored, retuned))
        held_out = self.held_out[positions]
        if int(held_out.sum()) > 1:
            self.log(DESCRIPTOR_VALIDATION_NDCG, self._held_out_ndcg(stored[held_out], positions[held_out]))

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        return scheduled_over_the_run(self, self.parameters(), learning_rate=self._learning_rate)

    def _loss_parts(self, batch: DescriptorBatch) -> DescriptorLossParts:
        """The training loss over one batch, with the label term over the taught labels it carries."""
        positions, stored_grid, retuned_grid, stored_duration, retuned_duration = batch
        stored = self(stored_grid, stored_duration)
        retuned = self(retuned_grid, retuned_duration)
        rows = self.label_position[positions]
        labeled = torch.nonzero((rows != NO_LABEL) & ~self.held_out[positions])[:, 0]
        label_rows = rows[labeled]
        targets = DescriptorTargets(
            teacher=self.teacher[positions], labeled=labeled, agreements=self.agreements[label_rows][:, label_rows]
        )
        return descriptor_loss(stored, retuned, targets=targets, weights=self._weights)

    def _held_out_ndcg(self, vectors: Tensor, positions: Tensor) -> float:
        rows = self.label_position[positions].cpu().numpy()
        agreements = self.agreements.cpu().numpy()[rows][:, rows]
        ranking = nearest_first(vectors.cpu().numpy(), groups=np.arange(len(rows), dtype=np.int64))
        return float(np.nanmean(ndcg_per_query(agreements, ranking, neighborhood=VALIDATION_NEIGHBORHOOD)))


def _retune_rank_one(stored: Tensor, retuned: Tensor) -> Tensor:
    """The share of retuned readings whose nearest stored reading is their own sound."""
    similarities = retuned @ stored.T
    return (similarities.argmax(dim=1) == torch.arange(stored.shape[0], device=stored.device)).float().mean()
