from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.morph_path.readings import (
    HeardPath,
    PathPoint,
    PathReadings,
    read_path,
    transposition_distances_db,
)
from tests.samplemorph.conftest import harmonic_tone

FRAME_COUNT: Final[int] = 16384
WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.5, 1.0)
DISSOLVE_PEAK_RATIO_FLOOR: Final[float] = 1.6
END_TOLERANCE_DB: Final[float] = 1e-6


def _tone(frequency: float) -> NDArray[np.float64]:
    return harmonic_tone(FRAME_COUNT, frequency=frequency)[:, 0]


@pytest.fixture(scope="module")
def dissolve() -> PathReadings:
    """Two tones mixed at every weight: the ends are the tones themselves, and the middle holds both at once."""
    first, second = _tone(220.0), _tone(330.0)
    points = tuple(
        PathPoint(weight=weight, waveform=np.sqrt(1.0 - weight) * first + np.sqrt(weight) * second)
        for weight in WEIGHTS
    )
    return read_path(HeardPath(points=points, first=first, second=second, rate_hz=NOMINAL_WAV_RATE))


def test_ends_rendered_as_the_sounds_themselves_cost_nothing(dissolve: PathReadings) -> None:
    assert dissolve.first_end.held_out_db == pytest.approx(0.0, abs=END_TOLERANCE_DB)
    assert dissolve.second_end.held_out_db == pytest.approx(0.0, abs=END_TOLERANCE_DB)


def test_a_dissolve_holds_the_peaks_of_both_ends_at_once(dissolve: PathReadings) -> None:
    assert dissolve.points[1].screen.peak_count_ratio >= DISSOLVE_PEAK_RATIO_FLOOR


def test_an_equal_power_dissolve_holds_its_loudness(dissolve: PathReadings) -> None:
    assert dissolve.largest_dip_lu < 1.0


def test_a_point_at_its_reference_reads_no_transposition_distance() -> None:
    points = (PathPoint(weight=0.5, waveform=_tone(261.0)),)

    assert transposition_distances_db(points, points) == (pytest.approx(0.0),)


def test_a_reference_at_another_weight_is_refused() -> None:
    tone = _tone(261.0)

    with pytest.raises(ValueError):
        transposition_distances_db((PathPoint(weight=0.5, waveform=tone),), (PathPoint(weight=0.25, waveform=tone),))
