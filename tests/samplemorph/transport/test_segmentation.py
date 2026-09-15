from __future__ import annotations

import numpy as np
import pytest

from samplemorph.transport.segmentation import LOWEST_MOVED_BIN, segment_spectrum

BIN_COUNT = 200
PROMINENCE_DB = 12.0


def _lobe(center: float, *, level: float = 1.0, spread: float = 1.0) -> np.ndarray:
    bins = np.arange(BIN_COUNT)
    lobe: np.ndarray = level * np.exp(-0.5 * ((bins - center) / spread) ** 2)
    return lobe


def _two_partials() -> np.ndarray:
    spectrum = _lobe(40.0) + _lobe(120.0, level=0.5) + 1e-6
    return spectrum / spectrum.sum()


def test_every_moved_bin_belongs_to_exactly_one_grain_and_groups_hold_their_grains_together() -> None:
    spectrum = _two_partials()

    groups = segment_spectrum(spectrum, spectrum, prominence_db=PROMINENCE_DB)

    assert groups.grain_starts[0] == LOWEST_MOVED_BIN
    assert groups.grain_ends[-1] == BIN_COUNT
    assert np.array_equal(groups.grain_starts[1:], groups.grain_ends[:-1])
    assert np.all(np.diff(groups.grain_groups) >= 0)
    assert groups.grain_energy.sum() == pytest.approx(spectrum[LOWEST_MOVED_BIN:].sum())


def test_each_prominent_partial_makes_a_group_centered_on_it() -> None:
    spectrum = _two_partials()

    groups = segment_spectrum(spectrum, spectrum, prominence_db=PROMINENCE_DB)

    assert groups.group_count == 2
    assert np.allclose(groups.group_center, [40.0, 120.0], atol=0.5)
    assert groups.group_energy[0] == pytest.approx(2.0 * groups.group_energy[1], rel=1e-3)


def test_a_bump_short_of_the_prominence_joins_its_neighbor() -> None:
    spectrum = _lobe(40.0) + _lobe(44.0, level=0.2) + 1e-6
    spectrum /= spectrum.sum()

    groups = segment_spectrum(spectrum, spectrum, prominence_db=PROMINENCE_DB)

    assert groups.group_count == 1
    assert groups.grain_starts.size >= 2
