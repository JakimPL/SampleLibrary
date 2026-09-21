from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.auditory.strikes import MAIN_STRIKE_DEPTH_DB, main_onset, read_strikes

SAMPLE_RATE_HZ = 44100
TONE_HZ = 220.0
HIT_DECAY_NEPERS_PER_SECOND = 30.0
ONSET_TOLERANCE_SECONDS = 0.02


def _hit(seconds: float, *, delay_seconds: float, level: float = 1.0) -> np.ndarray:
    times = np.arange(int(seconds * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ
    since = times - delay_seconds
    envelope = np.where(since >= 0.0, np.exp(-HIT_DECAY_NEPERS_PER_SECOND * np.maximum(since, 0.0)), 0.0)
    return level * envelope * np.sin(2.0 * np.pi * TONE_HZ * times)


def _swell(seconds: float) -> np.ndarray:
    times = np.arange(int(seconds * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ
    return (times / seconds) ** 2 * np.sin(2.0 * np.pi * TONE_HZ * times)


@dataclass(frozen=True)
class OnsetCase:
    name: str
    mono: np.ndarray
    expected_seconds: float


ONSET_CASES = (
    OnsetCase("hit at the start", _hit(0.5, delay_seconds=0.0), 0.0),
    OnsetCase("hit after silence", _hit(0.5, delay_seconds=0.15), 0.15),
    OnsetCase(
        "quiet pickup before the hit", _hit(0.6, delay_seconds=0.05, level=0.05) + _hit(0.6, delay_seconds=0.3), 0.3
    ),
)


@pytest.mark.parametrize("case", ONSET_CASES, ids=lambda case: case.name)
def test_the_main_onset_sits_at_the_attack_of_the_loudest_early_strike(case: OnsetCase) -> None:
    onset_seconds = main_onset(case.mono, sample_rate_hz=SAMPLE_RATE_HZ) / SAMPLE_RATE_HZ

    assert abs(onset_seconds - case.expected_seconds) <= ONSET_TOLERANCE_SECONDS


def test_a_slow_swell_begins_where_it_has_risen_within_the_depth_of_its_peak() -> None:
    seconds = 1.0
    swell = _swell(seconds)
    risen_seconds = seconds * 10.0 ** (-MAIN_STRIKE_DEPTH_DB / 40.0)

    onset_seconds = main_onset(swell, sample_rate_hz=SAMPLE_RATE_HZ) / SAMPLE_RATE_HZ

    assert abs(onset_seconds - risen_seconds) <= ONSET_TOLERANCE_SECONDS


def test_a_loop_of_hits_is_cut_hit_by_hit_and_the_strikes_cover_the_clip_once() -> None:
    loop = sum(_hit(1.0, delay_seconds=delay) for delay in (0.1, 0.4, 0.7))

    strikes = read_strikes(loop, sample_rate_hz=SAMPLE_RATE_HZ)

    assert strikes.starts.size == 4
    assert strikes.starts[0] == 0
    assert strikes.ends[-1] == loop.shape[0]
    assert np.array_equal(strikes.starts[1:], strikes.ends[:-1])
