from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor


@dataclass(frozen=True)
class Readout:
    """Where one distribution places its pitch, in bins, and how much of its mass stands there.

    Shapes: both are ``(batch,)``. `mass` lies in ``[0, 1]`` and says how far the answer is gathered
    in one place, which is what a reading of a sound with no pitch lacks.
    """

    bins: Tensor
    mass: Tensor


@dataclass(frozen=True)
class SoundReadout:
    """What a sound's frames answer together, each frame's answer weighed by the mass standing on it.

    Shapes: all three are ``(batch,)``. `bins` is the pitch, `mass` how gathered the frames' answers
    are on average, and `agreement` the share of that mass lying within a reach of the pitch, which
    tells a sound heard at one pitch from frames answering in every direction.
    """

    bins: Tensor
    mass: Tensor
    agreement: Tensor

    @property
    def reliability(self) -> Tensor:
        return self.mass * self.agreement


def read_distribution(distributions: Tensor, *, reach_bins: int) -> Readout:
    """Read each distribution's pitch as the mean of the bins within `reach_bins` of its peak, weighted by their mass.

    The peak alone answers to the nearest bin; the mean over its neighbors answers between bins,
    which is what a pitch between two of them asks for. Mass beyond the reach belongs to another
    peak, an octave away or elsewhere, and says the answer is less sure rather than moving it.
    Shape: `distributions` is ``(batch, bins)``.
    """
    peaks = distributions.argmax(dim=-1)
    offsets = torch.arange(-reach_bins, reach_bins + 1, device=distributions.device)
    positions = (peaks[:, None] + offsets[None, :]).clamp(0, distributions.shape[-1] - 1)
    weights = distributions.gather(1, positions)
    mass = weights.sum(dim=-1)
    bins = (weights * positions.to(distributions.dtype)).sum(dim=-1) / mass.clamp_min(torch.finfo(weights.dtype).tiny)
    return Readout(bins=bins, mass=mass)


def read_sound(distributions: Tensor, *, valid: Tensor, reach_bins: int) -> SoundReadout:
    """Read a sound's frames into one pitch: the median of their answers, weighted by the mass each one gathered.

    A median takes the pitch most of the sound's mass stands at, so a frame answering an octave
    away moves it not at all while it lowers the agreement. Shapes: `distributions` is
    ``(batch, frames, bins)`` and `valid` ``(batch, frames)``, false where a sound kept fewer frames
    than the batch holds.
    """
    batch, frames, bins = distributions.shape
    frame_readout = read_distribution(distributions.reshape(batch * frames, bins), reach_bins=reach_bins)
    positions = frame_readout.bins.reshape(batch, frames)
    weights = frame_readout.mass.reshape(batch, frames) * valid
    total = weights.sum(dim=-1)
    floor = torch.finfo(weights.dtype).tiny
    pitch = weighted_median(positions, weights=weights)
    agreed = torch.where((positions - pitch[:, None]).abs() <= reach_bins, weights, torch.zeros_like(weights))
    return SoundReadout(
        bins=pitch,
        mass=total / valid.sum(dim=-1).clamp_min(1.0),
        agreement=agreed.sum(dim=-1) / total.clamp_min(floor),
    )


def weighted_median(values: Tensor, *, weights: Tensor) -> Tensor:
    """The value each row's weight is half below and half above. Shapes: both ``(batch, count)``, the result ``(batch,)``."""
    ordered, order = values.sort(dim=-1)
    gathered = weights.gather(-1, order)
    reached = (gathered.cumsum(dim=-1) < 0.5 * gathered.sum(dim=-1, keepdim=True)).sum(dim=-1)
    return ordered.gather(-1, reached.clamp(max=values.shape[-1] - 1)[:, None])[:, 0]
