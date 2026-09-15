from __future__ import annotations

import numpy as np
import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import build_time_map, interpolated_sample_count
from tests.samplemorph.transport.conftest import GEOMETRY, analysis_of, decaying, tone

HOP = GEOMETRY.hop_length


def test_a_length_between_two_is_the_geometric_one() -> None:
    assert interpolated_sample_count(1000, 4000, weight=0.5) == 2000
    assert interpolated_sample_count(1000, 4000, weight=0.0) == 1000
    assert interpolated_sample_count(1000, 4000, weight=1.0) == 4000


def test_at_an_end_the_map_reads_that_end_frame_by_frame() -> None:
    first = analysis_of(decaying(tone(440.0), time_constant_seconds=0.05))
    second = analysis_of(decaying(tone(440.0, frame_count=8192), time_constant_seconds=0.2, delay_seconds=0.05))

    time_map = build_time_map(first, second, weight=0.0, hop_length=HOP, settings=TransportSettings())

    assert time_map.sample_count == first.sample_count
    assert np.allclose(time_map.first_positions, np.arange(first.frame_count), atol=1e-6)


def test_every_map_runs_forward_through_both_sources() -> None:
    first = analysis_of(decaying(tone(440.0), time_constant_seconds=0.02))
    second = analysis_of(decaying(tone(440.0, frame_count=8192), time_constant_seconds=0.3, delay_seconds=0.05))

    for weight in (0.25, 0.5, 0.75):
        time_map = build_time_map(first, second, weight=weight, hop_length=HOP, settings=TransportSettings())
        assert np.all(np.diff(time_map.first_positions) > 0.0)
        assert np.all(np.diff(time_map.second_positions) > 0.0)
        assert time_map.first_rates.shape == time_map.first_positions.shape


def test_the_onsets_of_both_sources_meet_at_one_output_moment() -> None:
    delay_seconds = 0.1
    early = analysis_of(decaying(tone(440.0), time_constant_seconds=0.05))
    late = analysis_of(decaying(tone(440.0), time_constant_seconds=0.05, delay_seconds=delay_seconds))

    time_map = build_time_map(early, late, weight=0.5, hop_length=HOP, settings=TransportSettings())

    output_times = np.arange(time_map.frame_count) * HOP
    early_meets = np.interp(early.onset_sample / HOP, time_map.first_positions, output_times)
    late_meets = np.interp(late.onset_sample / HOP, time_map.second_positions, output_times)
    assert early_meets == pytest.approx(late_meets, abs=HOP)
    assert 0.0 < early_meets / NOMINAL_WAV_RATE < delay_seconds
