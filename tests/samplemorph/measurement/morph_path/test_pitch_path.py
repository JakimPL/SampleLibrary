from __future__ import annotations

import math
from typing import Final

import pytest

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.coordinates.readers import PyinReader, pyin_reader
from samplemorph.measurement.morph_path.pitch_path import PitchPath, heard_pitch, is_pitched_pair
from tests.samplemorph.conftest import harmonic_tone, noise_burst

FRAME_COUNT: Final[int] = 16384
STEP_COUNT: Final[int] = 8
WEIGHTS: Final[tuple[float, ...]] = tuple(index / STEP_COUNT for index in range(STEP_COUNT + 1))
OCTAVE_SEMITONES: Final[float] = 12.0
PITCH_TOLERANCE_SEMITONES: Final[float] = 0.5


@pytest.fixture(scope="module")
def reader() -> PyinReader:
    return pyin_reader()


def test_a_glide_over_even_steps_moves_one_step_of_its_span_at_a_time() -> None:
    path = PitchPath(weights=WEIGHTS, semitones=tuple(-12.0 + 7.0 * weight for weight in WEIGHTS))

    assert path.jump_share == pytest.approx(1.0 / STEP_COUNT)
    assert path.largest_deviation_semitones == pytest.approx(0.0, abs=1e-9)


def test_a_switch_moves_its_whole_span_in_one_step() -> None:
    path = PitchPath(weights=WEIGHTS, semitones=tuple(-12.0 if weight < 0.5 else -5.0 for weight in WEIGHTS))

    assert path.jump_share == pytest.approx(1.0)
    assert path.largest_deviation_semitones == pytest.approx(3.5)


def test_a_path_with_a_point_of_no_pitch_has_no_steps_to_read() -> None:
    path = PitchPath(weights=WEIGHTS, semitones=tuple(float("nan") if weight == 0.5 else weight for weight in WEIGHTS))

    assert not path.is_read
    assert math.isnan(path.jump_share)
    assert math.isnan(path.largest_deviation_semitones)


def test_frames_played_at_twice_the_rate_are_heard_an_octave_higher(reader: PyinReader) -> None:
    tone = harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0]

    lower = heard_pitch(tone, rate_hz=NOMINAL_WAV_RATE / 2.0, reader=reader)
    higher = heard_pitch(tone, rate_hz=NOMINAL_WAV_RATE, reader=reader)

    assert higher - lower == pytest.approx(OCTAVE_SEMITONES, abs=PITCH_TOLERANCE_SEMITONES)


def test_two_tones_a_fifth_apart_have_a_pitch_path(reader: PyinReader) -> None:
    first = harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0]
    second = harmonic_tone(FRAME_COUNT, frequency=330.0)[:, 0]

    assert is_pitched_pair(first, second, rate_hz=NOMINAL_WAV_RATE, reader=reader)


def test_one_note_twice_or_an_unpitched_end_leave_no_pitch_path(reader: PyinReader) -> None:
    tone = harmonic_tone(FRAME_COUNT, frequency=220.0)[:, 0]
    burst = noise_burst(FRAME_COUNT, seed=5)[:, 0]

    assert not is_pitched_pair(tone, tone, rate_hz=NOMINAL_WAV_RATE, reader=reader)
    assert not is_pitched_pair(tone, burst, rate_hz=NOMINAL_WAV_RATE, reader=reader)
