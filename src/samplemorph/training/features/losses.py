from __future__ import annotations

from typing import Final

import torch
from torch import Tensor

# The critic reads a share folded onto [0, 0.5]: a line is walked from either end, so a share and
# its complement describe the same point.
MAXIMUM_SHARE: Final[float] = 0.5


def drawn_shares(count: int, *, device: torch.device) -> Tensor:
    """One mixing share per interpolant, uniform on [0, `MAXIMUM_SHARE`]."""
    return torch.rand(count, device=device) * MAXIMUM_SHARE


def spread_shares(count: int, *, device: torch.device) -> Tensor:
    """Shares evenly over [0, `MAXIMUM_SHARE`], the same for every validation batch of one size."""
    return torch.linspace(0.0, MAXIMUM_SHARE, count, device=device)


def interpolated(latents: Tensor, shares: Tensor) -> Tensor:
    """Every latent mixed with its neighbor in the batch, `shares` of the way from the neighbor to itself.

    Rolling the batch by one pairs every sample with another whenever the batch holds two or more.
    Shapes: `latents` ``(batch, latent)``, `shares` ``(batch,)``.
    """
    weights = shares[:, None]
    return weights * latents + (1.0 - weights) * torch.roll(latents, shifts=1, dims=0)


def realistic_mix(grids: Tensor, reconstructions: Tensor, *, mix: float) -> Tensor:
    """Sounds mixed `mix` of the way into their own reconstructions, which the critic learns to read as sounds."""
    return mix * grids + (1.0 - mix) * reconstructions


def adversarial_term(interpolant_scores: Tensor) -> Tensor:
    """How far the critic sees the interpolants from sounds, which the autoencoder is taught to shrink."""
    return (interpolant_scores**2).mean()


def critic_error(interpolant_scores: Tensor, shares: Tensor) -> Tensor:
    """How far the critic's reading of every interpolant misses the share it was mixed at."""
    return ((interpolant_scores - shares) ** 2).mean()


def critic_loss(interpolant_scores: Tensor, shares: Tensor, *, realistic_scores: Tensor) -> Tensor:
    """The critic's objective: the share every interpolant was mixed at, and 0 for every sound."""
    return critic_error(interpolant_scores, shares) + (realistic_scores**2).mean()
