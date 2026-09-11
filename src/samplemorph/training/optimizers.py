from __future__ import annotations

from collections.abc import Iterable

import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import LRSchedulerConfigType, OptimizerLRSchedulerConfig
from torch import Tensor


def cosine_optimizer(
    parameters: Iterable[Tensor], *, learning_rate: float, total_steps: int
) -> OptimizerLRSchedulerConfig:
    """AdamW under a rate that falls over the whole run rather than over each epoch.

    The schedule is told how many steps the run will take, so a rate reaching its floor at the end
    holds whatever the corpus size and batch size work out to.
    """
    optimizer = torch.optim.AdamW(parameters, lr=learning_rate)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(total_steps, 1))
    return OptimizerLRSchedulerConfig(
        optimizer=optimizer, lr_scheduler=LRSchedulerConfigType(scheduler=schedule, interval="step")
    )


def scheduled_over_the_run(
    module: LightningModule, parameters: Iterable[Tensor], *, learning_rate: float
) -> OptimizerLRSchedulerConfig:
    """`cosine_optimizer` over the number of steps the module's trainer has planned for the whole run."""
    return cosine_optimizer(
        parameters, learning_rate=learning_rate, total_steps=int(module.trainer.estimated_stepping_batches)
    )
