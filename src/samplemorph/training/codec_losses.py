from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor
from torch.nn import functional

DEFAULT_RECONSTRUCTION_WEIGHT: Final[float] = 1.0
DEFAULT_PRIOR_WEIGHT: Final[float] = 0.01
DEFAULT_CYCLE_WEIGHT: Final[float] = 0.1
# The grid is read at its own resolution and at two coarser ones, so a decoder is scored on the
# shape of a spectrum as well as on its lines.
COARSER_READINGS: Final[tuple[tuple[int, int], ...]] = ((4, 2), (16, 4))


@dataclass(frozen=True)
class CodecLossWeights:
    """How much each of the three terms says in the total.

    Reconstruction is what the codec is for. The prior on the residual is what makes a point between
    two residuals decode to something, and its weight is the trade between fidelity and a latent
    that interpolates. The cycle term asks the decoded grid to describe as the descriptor it was
    decoded from, which is what makes the decoder use its conditioning.
    """

    reconstruction: float = DEFAULT_RECONSTRUCTION_WEIGHT
    prior: float = DEFAULT_PRIOR_WEIGHT
    cycle: float = DEFAULT_CYCLE_WEIGHT


@dataclass(frozen=True)
class CodecPrediction:
    """What the codec produced for one batch: the grid, the residual's posterior, and how the grid describes."""

    grid: Tensor
    mean: Tensor
    log_variance: Tensor
    described: Tensor


@dataclass(frozen=True)
class CodecLossParts:
    reconstruction: Tensor
    prior: Tensor
    cycle: Tensor
    total: Tensor


def reconstruction_error(predicted: Tensor, target: Tensor) -> Tensor:
    """Mean absolute difference over the grid and over its coarser readings, averaged."""
    errors = [functional.l1_loss(predicted, target)]
    for band_pool, column_pool in COARSER_READINGS:
        # pylint: disable-next=not-callable
        pooled_predicted = functional.avg_pool2d(predicted[:, None], (band_pool, column_pool))
        # pylint: disable-next=not-callable
        pooled_target = functional.avg_pool2d(target[:, None], (band_pool, column_pool))
        errors.append(functional.l1_loss(pooled_predicted, pooled_target))
    return torch.stack(errors).mean()


def prior_divergence(mean: Tensor, log_variance: Tensor) -> Tensor:
    """How far the residual's posterior sits from the unit Gaussian, per dimension on average."""
    return 0.5 * (torch.exp(log_variance) + mean**2 - 1.0 - log_variance).mean()


def cycle_error(described: Tensor, descriptor: Tensor) -> Tensor:
    """How far the decoded grid's description turns from the descriptor it was decoded from."""
    return (1.0 - (described * descriptor).sum(dim=-1)).mean()


def codec_loss(
    prediction: CodecPrediction, *, target: Tensor, descriptor: Tensor, weights: CodecLossWeights, prior_share: float
) -> CodecLossParts:
    """The three terms and their weighted sum; `prior_share` scales the prior's weight during its warm-up."""
    reconstruction = reconstruction_error(prediction.grid, target)
    prior = prior_divergence(prediction.mean, prediction.log_variance)
    cycle = cycle_error(prediction.described, descriptor)
    total = weights.reconstruction * reconstruction + weights.prior * prior_share * prior + weights.cycle * cycle
    return CodecLossParts(reconstruction=reconstruction, prior=prior, cycle=cycle, total=total)
