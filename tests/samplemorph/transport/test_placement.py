from __future__ import annotations

import numpy as np
import pytest

from samplemorph.transport.placement import place_groups
from samplemorph.transport.segmentation import segment_spectrum

BIN_COUNT = 256
PROMINENCE_DB = 12.0
LOBE_SPREAD_BINS = 1.2


def _lobe_spectrum(center: float) -> np.ndarray:
    bins = np.arange(BIN_COUNT)
    spectrum = np.exp(-0.5 * ((bins - center) / LOBE_SPREAD_BINS) ** 2) + 1e-12
    return spectrum / spectrum.sum()


def _place(spectrum: np.ndarray, *, scale: float, gain: float = 1.0) -> np.ndarray:
    groups = segment_spectrum(spectrum, spectrum, prominence_db=PROMINENCE_DB)
    return place_groups(
        spectrum,
        groups,
        piece_groups=np.arange(groups.group_count),
        piece_gains=np.full(groups.group_count, gain),
        piece_scales=np.full(groups.group_count, scale),
    )


def test_a_group_left_in_place_is_deposited_as_it_was() -> None:
    spectrum = _lobe_spectrum(60.0)

    placed = _place(spectrum, scale=1.0)

    assert np.allclose(placed[1:], spectrum[1:], rtol=1e-9, atol=1e-15)


def test_a_partial_moved_by_a_scale_keeps_its_lobe_and_its_energy() -> None:
    spectrum = _lobe_spectrum(60.0)

    placed = _place(spectrum, scale=1.5, gain=0.5)

    bins = np.arange(BIN_COUNT)
    center = float((placed * bins).sum() / placed.sum())
    spread = float(np.sqrt((placed * (bins - center) ** 2).sum() / placed.sum()))
    assert center == pytest.approx(90.0, abs=0.1)
    assert spread == pytest.approx(LOBE_SPREAD_BINS, rel=0.05)
    assert placed.sum() == pytest.approx(0.5 * spectrum[1:].sum(), rel=1e-6)


def test_what_is_carried_past_the_last_bin_leaves_the_spectrum() -> None:
    spectrum = _lobe_spectrum(200.0)

    placed = _place(spectrum, scale=2.0)

    assert placed.sum() < 1e-6
