from __future__ import annotations

import pytest
from trackmod.core.notes.pitch import Note
from trackmod.spec.pitch import RATE_NOTE, REFERENCE_RATE

from samplecore.pitch import sounding_rate_hz

RATE_KEY = Note(RATE_NOTE)


def test_the_reference_key_sounds_at_the_stored_rate_itself() -> None:
    assert sounding_rate_hz(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY) == pytest.approx(REFERENCE_RATE)


def test_an_octave_above_the_reference_key_doubles_the_rate() -> None:
    rate = sounding_rate_hz(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY.transposed(12))

    assert rate == pytest.approx(REFERENCE_RATE * 2)


def test_an_octave_below_the_reference_key_halves_the_rate() -> None:
    rate = sounding_rate_hz(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY.transposed(-12))

    assert rate == pytest.approx(REFERENCE_RATE / 2)


def test_a_semitone_moves_the_rate_by_the_equal_tempered_ratio() -> None:
    rate = sounding_rate_hz(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY.transposed(1))

    assert rate == pytest.approx(REFERENCE_RATE * 2 ** (1 / 12))


def test_the_rate_scales_with_the_occurrence_it_is_read_against() -> None:
    """Two occurrences of one waveform at different reference rates sound the same note differently."""
    quiet = sounding_rate_hz(reference_rate_hz=8363, sounded_note=RATE_KEY.transposed(7))
    loud = sounding_rate_hz(reference_rate_hz=16726, sounded_note=RATE_KEY.transposed(7))

    assert loud == pytest.approx(quiet * 2)
