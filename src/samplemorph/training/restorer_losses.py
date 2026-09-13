from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor

# (bins, frames) spans averaged before the coarser comparisons: a line the restorer misplaces by
# a bin still reads right at the first pooling, and a spectral shape it gets wrong reads wrong at
# every one, so the fine term teaches placement and the coarse terms teach shape.
COARSE_POOLINGS: Final[tuple[tuple[int, int], ...]] = ((4, 2), (16, 4))


@dataclass(frozen=True)
class RestorerLossParts:
    """The distance between a restored magnitude and the clean analysis, in decibels over the range.

    `fine` compares bin by bin; `coarse` compares the same pair after averaging over each of
    `COARSE_POOLINGS`, taken together. The total weighs every comparison the same, so an epoch's
    number reads as one mean absolute error in the restorer's own units.
    """

    fine: Tensor
    coarse: Tensor

    @property
    def total(self) -> Tensor:
        return (self.fine + self.coarse * len(COARSE_POOLINGS)) / (1 + len(COARSE_POOLINGS))


def restorer_loss(predicted: Tensor, target: Tensor) -> RestorerLossParts:
    """Mean absolute error at native resolution and at each coarser pooling, for ``(batch, bins, frames)`` decibels."""
    fine = torch.nn.functional.l1_loss(predicted, target)
    coarse = torch.zeros((), dtype=predicted.dtype, device=predicted.device)
    for pooling in COARSE_POOLINGS:
        # pylint: disable-next=not-callable
        pooled_prediction = torch.nn.functional.avg_pool2d(predicted[:, None], pooling)
        # pylint: disable-next=not-callable
        pooled_target = torch.nn.functional.avg_pool2d(target[:, None], pooling)
        coarse = coarse + torch.nn.functional.l1_loss(pooled_prediction, pooled_target)
    return RestorerLossParts(fine=fine, coarse=coarse / len(COARSE_POOLINGS))
