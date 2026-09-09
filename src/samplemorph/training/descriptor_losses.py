from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor
from torch.nn import functional

CONTRAST_TEMPERATURE: Final[float] = 0.1
DEFAULT_DISTILLATION_WEIGHT: Final[float] = 1.0
DEFAULT_RETUNING_WEIGHT: Final[float] = 0.5
DEFAULT_LABEL_WEIGHT: Final[float] = 0.5
# A logit this low leaves a masked pair with no share of the softmax at any temperature used here.
MASKED_LOGIT: Final[float] = -1e9


@dataclass(frozen=True)
class DescriptorLossWeights:
    """How much each of the three signals says in the total.

    The teacher supplies what sounds alike to people, the retuned views supply that a retuning
    changes nothing, and the labels supply what this listener called alike. Measured on a pilot,
    the retuning term buys the octave at a cost in agreement that the label term buys back, so its
    weight is the one worth sweeping.
    """

    distillation: float = DEFAULT_DISTILLATION_WEIGHT
    retuning: float = DEFAULT_RETUNING_WEIGHT
    labels: float = DEFAULT_LABEL_WEIGHT


@dataclass(frozen=True)
class DescriptorTargets:
    """What one batch is scored against: each sound's teacher vector, and the agreements among its labeled rows.

    `labeled` picks the rows of the batch that carry a taught label, in the order `agreements`
    names them.
    """

    teacher: Tensor
    labeled: Tensor
    agreements: Tensor


@dataclass(frozen=True)
class DescriptorLossParts:
    distillation: Tensor
    retuning: Tensor
    labels: Tensor
    total: Tensor


def distillation_error(student: Tensor, teacher: Tensor) -> Tensor:
    """How far, on average, the student's unit vectors turn from the teacher's."""
    return (1.0 - (student * teacher).sum(dim=-1)).mean()


def retuning_contrast(first: Tensor, second: Tensor, *, temperature: float) -> Tensor:
    """Each sound's two readings find each other among the batch, read from both sides.

    `first` and `second` hold the same sounds in the same order, one as stored and one retuned, so
    the matching row is the one positive and every other row a negative.
    """
    logits = first @ second.T / temperature
    targets = torch.arange(first.shape[0], device=first.device)
    return 0.5 * (functional.cross_entropy(logits, targets) + functional.cross_entropy(logits.T, targets))


def label_contrast(embeddings: Tensor, agreements: Tensor, *, temperature: float) -> Tensor:
    """Each labeled sound's neighborhood is asked to match how much the labels agree.

    The softmax over a sound's similarities to the other labeled sounds is scored against their
    agreements, normalized to a distribution, so a sound is pulled toward everything that shares a
    tag in proportion to how much it shares. A sound agreeing with nothing in the batch has no
    target and is left out; the whole term is zero when none has one.
    """
    logits = embeddings @ embeddings.T / temperature
    logits = logits.masked_fill(torch.eye(len(embeddings), dtype=torch.bool, device=embeddings.device), MASKED_LOGIT)
    has_positive = agreements.sum(dim=1) > 0.0
    if not bool(has_positive.any()):
        return torch.zeros((), device=embeddings.device)
    targets = agreements[has_positive] / agreements[has_positive].sum(dim=1, keepdim=True)
    return -(targets * functional.log_softmax(logits[has_positive], dim=1)).sum(dim=1).mean()


def descriptor_loss(
    stored: Tensor, retuned: Tensor, *, targets: DescriptorTargets, weights: DescriptorLossWeights
) -> DescriptorLossParts:
    """The three terms and their weighted sum, for one batch's stored and retuned readings."""
    distillation = 0.5 * (distillation_error(stored, targets.teacher) + distillation_error(retuned, targets.teacher))
    retuning = retuning_contrast(stored, retuned, temperature=CONTRAST_TEMPERATURE)
    labels = label_contrast(stored[targets.labeled], targets.agreements, temperature=CONTRAST_TEMPERATURE)
    total = weights.distillation * distillation + weights.retuning * retuning + weights.labels * labels
    return DescriptorLossParts(distillation=distillation, retuning=retuning, labels=labels, total=total)
