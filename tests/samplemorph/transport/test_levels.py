from __future__ import annotations

import pytest

from samplemorph.transport.levels import level_path

LOUDNESS_EXPONENT = 1.0 / 3.0


def test_a_level_path_returns_each_end_and_stays_between_them() -> None:
    assert level_path(8.0, 1.0, weight=0.0, exponent=LOUDNESS_EXPONENT) == pytest.approx(8.0)
    assert level_path(8.0, 1.0, weight=1.0, exponent=LOUDNESS_EXPONENT) == pytest.approx(1.0)
    assert 1.0 < level_path(8.0, 1.0, weight=0.5, exponent=LOUDNESS_EXPONENT) < 8.0


def test_a_level_meeting_silence_arrives_halfway_as_half_as_loud() -> None:
    assert level_path(1.0, 0.0, weight=0.5, exponent=LOUDNESS_EXPONENT) == pytest.approx(0.125)
