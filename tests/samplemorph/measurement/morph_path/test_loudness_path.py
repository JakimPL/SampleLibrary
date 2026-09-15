from __future__ import annotations

import math
from typing import Final

import pytest

from samplemorph.measurement.morph_path.loudness_path import LoudnessPath

WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.5, 1.0)


def test_a_path_on_the_line_reads_no_offset_and_no_dip() -> None:
    path = LoudnessPath(weights=WEIGHTS, loudness_lufs=(-20.0, -15.0, -10.0))

    assert path.line_offset_lu(1) == pytest.approx(0.0)
    assert path.largest_dip_lu == 0.0


def test_a_quiet_middle_reads_how_far_it_dips() -> None:
    path = LoudnessPath(weights=WEIGHTS, loudness_lufs=(-20.0, -21.0, -10.0))

    assert path.largest_dip_lu == pytest.approx(6.0)


def test_the_sone_line_runs_above_the_loudness_line_between_unequal_ends() -> None:
    path = LoudnessPath(weights=WEIGHTS, loudness_lufs=(-20.0, -15.0, -10.0))
    sone_line = 10.0 * math.log2(0.5 * 2.0**-2.0 + 0.5 * 2.0**-1.0)

    assert path.sone_offset_lu(1) == pytest.approx(-15.0 - sone_line)
    assert path.sone_offset_lu(1) < path.line_offset_lu(1)


def test_a_silent_point_reads_no_offset_and_leaves_the_dip_to_the_rest() -> None:
    path = LoudnessPath(weights=(0.0, 0.25, 0.5, 1.0), loudness_lufs=(-20.0, -math.inf, -18.0, -20.0))

    assert math.isnan(path.line_offset_lu(1))
    assert path.largest_dip_lu == 0.0
