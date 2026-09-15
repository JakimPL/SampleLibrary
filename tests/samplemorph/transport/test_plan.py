from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from samplemorph.transport.plan import monotone_plan

masses = arrays(np.float64, st.integers(1, 12), elements=st.floats(1e-3, 10.0))


@given(first=masses, second=masses)
def test_a_plan_carries_every_share_of_both_spectra_in_frequency_order(first: np.ndarray, second: np.ndarray) -> None:
    plan = monotone_plan(first, second)

    assert plan.masses.sum() == pytest.approx(1.0)
    assert np.allclose(np.bincount(plan.first_groups, plan.masses, minlength=first.size), first / first.sum())
    assert np.allclose(np.bincount(plan.second_groups, plan.masses, minlength=second.size), second / second.sum())
    assert np.all(np.diff(plan.first_groups) >= 0)
    assert np.all(np.diff(plan.second_groups) >= 0)
    assert plan.masses.size <= first.size + second.size - 1


def test_matching_spectra_pair_each_group_with_its_counterpart() -> None:
    spectrum = np.array([0.2, 0.5, 0.3])

    plan = monotone_plan(spectrum, 2.0 * spectrum)

    assert np.array_equal(plan.first_groups, [0, 1, 2])
    assert np.array_equal(plan.second_groups, [0, 1, 2])


def test_a_plan_between_nothing_and_something_is_refused() -> None:
    with pytest.raises(ValueError, match="each carry something"):
        monotone_plan(np.zeros(3), np.ones(3))
