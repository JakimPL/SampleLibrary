from __future__ import annotations

import torch
from torch import Tensor
from torch.nn import functional

HUBER_DELTA = 1.0


def pitch_projection(distributions: Tensor, *, ratio_per_bin: float) -> Tensor:
    """Read each distribution as one number that a shift multiplies: the sum of its mass by the frequency each bin stands at.

    A distribution moved `k` bins up reads `ratio_per_bin ** k` times as high whatever its shape, so
    the ratio of two readings says how far one lies from the other without either saying where it
    is. This is the projection PESTO's equivariance term is priced through (Riou et al., 2023).
    Shape: `distributions` is ``(batch, bins)``, the result ``(batch,)``.
    """
    bins = torch.arange(distributions.shape[-1], device=distributions.device, dtype=distributions.dtype)
    return (distributions * ratio_per_bin**bins).sum(dim=-1)


def equivariance_loss(first: Tensor, second: Tensor, *, shift_bins: Tensor, ratio_per_bin: float) -> Tensor:
    """How far two answers stand apart against how far their crops do, priced by a Huber loss.

    Two crops of one frame `k` bins apart must be answered `k` bins apart, whatever the answers
    themselves are, which is the one thing that makes the output a position rather than a label.
    """
    ratio = pitch_projection(second, ratio_per_bin=ratio_per_bin) / pitch_projection(
        first, ratio_per_bin=ratio_per_bin
    ).clamp_min(torch.finfo(first.dtype).tiny)
    return functional.huber_loss(ratio, ratio_per_bin ** shift_bins.to(ratio.dtype), delta=HUBER_DELTA)


def shifted_distribution(distributions: Tensor, *, shift_bins: Tensor) -> Tensor:
    """Every distribution moved along the bin axis by its own shift, what moves in from either end reading as nothing.

    Shapes: `distributions` is ``(batch, bins)`` and `shift_bins` ``(batch,)``.
    """
    bins = torch.arange(distributions.shape[-1], device=distributions.device)
    sources = bins[None, :] - shift_bins[:, None]
    inside = (sources >= 0) & (sources < distributions.shape[-1])
    gathered = distributions.gather(1, sources.clamp(0, distributions.shape[-1] - 1))
    return torch.where(inside, gathered, torch.zeros_like(gathered))


def shift_cross_entropy(prediction: Tensor, *, target: Tensor, shift_bins: Tensor) -> Tensor:
    """What the answer to a shifted crop costs against the answer to the other crop, moved by the shift between them.

    The ratio alone leaves a distribution free to spread as it likes; holding it against the moved
    one bin by bin asks the same shape to arrive in the new place.
    """
    return _cross_entropy(prediction, target=shifted_distribution(target.detach(), shift_bins=shift_bins))


def invariance_cross_entropy(first: Tensor, second: Tensor) -> Tensor:
    """What two answers to one crop under two augmentations cost against each other, each read as the other's target.

    Everything the two views differ in -- the body they sound through, the registers cut away, the
    noise under them -- is what a pitch is not, so the two answers must be one answer.
    """
    return 0.5 * (_cross_entropy(first, target=second.detach()) + _cross_entropy(second, target=first.detach()))


def _cross_entropy(prediction: Tensor, *, target: Tensor) -> Tensor:
    return -(target * prediction.clamp_min(torch.finfo(prediction.dtype).tiny).log()).sum(dim=-1).mean()
