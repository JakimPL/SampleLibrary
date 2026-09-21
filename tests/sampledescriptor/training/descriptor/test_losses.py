from __future__ import annotations

import pytest
import torch

from sampledescriptor.training.descriptor.losses import (
    CONTRAST_TEMPERATURE,
    DescriptorTargets,
    descriptor_loss,
    distillation_error,
    label_contrast,
    retuning_contrast,
)
from sampledescriptor.training.descriptor.settings import DescriptorLossWeights


def _unit(rows: int, size: int, seed: int) -> torch.Tensor:
    return torch.nn.functional.normalize(torch.randn(rows, size, generator=torch.Generator().manual_seed(seed)), dim=-1)


def test_a_student_matching_the_teacher_has_nothing_left_to_learn() -> None:
    teacher = _unit(4, 8, seed=0)

    assert distillation_error(teacher, teacher).item() == pytest.approx(0.0, abs=1e-6)
    assert distillation_error(-teacher, teacher).item() == pytest.approx(2.0, abs=1e-6)


def test_readings_that_find_each_other_score_lower_than_readings_that_do_not() -> None:
    stored = _unit(6, 8, seed=1)

    matched = retuning_contrast(stored, stored, temperature=CONTRAST_TEMPERATURE)
    shuffled = retuning_contrast(
        stored, stored[torch.randperm(6, generator=torch.Generator().manual_seed(2))], temperature=CONTRAST_TEMPERATURE
    )

    assert matched < shuffled


def test_the_label_term_pulls_toward_what_agrees_and_is_zero_with_nothing_to_agree_on() -> None:
    embeddings = _unit(3, 8, seed=3)
    agreements = torch.tensor([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])

    scored = label_contrast(embeddings, agreements, temperature=CONTRAST_TEMPERATURE)
    aligned = label_contrast(
        torch.stack([embeddings[0], embeddings[0], embeddings[2]]), agreements, temperature=CONTRAST_TEMPERATURE
    )

    assert aligned < scored
    assert label_contrast(embeddings, torch.zeros(3, 3), temperature=CONTRAST_TEMPERATURE).item() == 0.0


def test_the_total_weighs_the_three_terms_as_asked() -> None:
    stored = _unit(4, 8, seed=4)
    retuned = _unit(4, 8, seed=5)
    teacher = _unit(4, 8, seed=6)
    labeled = torch.tensor([0, 2])
    agreements = torch.tensor([[0.0, 0.5], [0.5, 0.0]])
    weights = DescriptorLossWeights(distillation=2.0, retuning=0.0, labels=1.0)

    targets = DescriptorTargets(teacher=teacher, labeled=labeled, agreements=agreements)

    parts = descriptor_loss(stored, retuned, targets=targets, weights=weights)

    torch.testing.assert_close(parts.total, 2.0 * parts.distillation + parts.labels)
