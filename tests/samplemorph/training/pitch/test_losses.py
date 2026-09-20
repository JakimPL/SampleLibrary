from __future__ import annotations

import pytest
import torch
from torch import Tensor

from samplemorph.training.pitch.losses import (
    equivariance_loss,
    invariance_cross_entropy,
    pitch_projection,
    shift_cross_entropy,
    shifted_distribution,
)

BIN_COUNT = 32
RATIO_PER_BIN = 2.0 ** (1.0 / 36.0)
EXACT = 1e-6


def _peaked(peaks: tuple[int, ...]) -> Tensor:
    distributions = torch.zeros(len(peaks), BIN_COUNT)
    for row, peak in enumerate(peaks):
        distributions[row, peak] = 1.0
    return distributions


def test_a_distribution_moved_up_three_bins_reads_three_bins_higher() -> None:
    first, second = _peaked((10,)), _peaked((13,))

    ratio = pitch_projection(second, ratio_per_bin=RATIO_PER_BIN) / pitch_projection(first, ratio_per_bin=RATIO_PER_BIN)

    assert float(ratio) == pytest.approx(RATIO_PER_BIN**3, abs=EXACT)


def test_two_answers_standing_exactly_the_shift_apart_cost_nothing() -> None:
    first, second = _peaked((10, 20)), _peaked((13, 17))

    loss = equivariance_loss(first, second, shift_bins=torch.tensor([3, -3]), ratio_per_bin=RATIO_PER_BIN)
    under_another_shift = equivariance_loss(first, second, shift_bins=torch.tensor([0, 0]), ratio_per_bin=RATIO_PER_BIN)

    assert float(loss) == pytest.approx(0.0, abs=EXACT)
    assert float(under_another_shift) > float(loss)


def test_a_distribution_moved_by_a_shift_carries_its_mass_and_leaves_behind_what_falls_off_the_axis() -> None:
    distributions = _peaked((10, 1))

    moved = shifted_distribution(distributions, shift_bins=torch.tensor([5, -5]))

    assert float(moved[0, 15]) == pytest.approx(1.0, abs=EXACT)
    assert float(moved[1].sum()) == pytest.approx(0.0, abs=EXACT)


def test_an_answer_landing_where_the_other_one_moved_to_costs_least() -> None:
    first, second = _peaked((10,)), _peaked((13,))

    at_the_shift = shift_cross_entropy(second, target=first, shift_bins=torch.tensor([3]))
    at_no_shift = shift_cross_entropy(second, target=first, shift_bins=torch.tensor([0]))

    assert float(at_the_shift) < float(at_no_shift)


def test_two_augmentations_answering_alike_cost_less_than_two_answering_apart() -> None:
    together, apart = _peaked((10,)), _peaked((22,))

    assert float(invariance_cross_entropy(together, together)) < float(invariance_cross_entropy(together, apart))
