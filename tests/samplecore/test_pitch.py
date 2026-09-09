from __future__ import annotations

from collections import Counter

import pytest
from trackmod.core.notes.pitch import Note
from trackmod.spec.pitch import RATE_NOTE, REFERENCE_RATE

from samplecore.models.note_event import SampleNoteUsage, SamplePlaybackRate
from samplecore.pitch import (
    choose_playback_rate,
    dominant_playback_rate,
    effective_playback_rate,
    playback_rates_of,
    sounding_rate_hz,
    tally_playback_rates,
)

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


def _usage(*, reference_rate_hz: int, semitones: int, event_count: int) -> SampleNoteUsage:
    return SampleNoteUsage(
        reference_rate_hz=reference_rate_hz,
        sounded_note=RATE_KEY.transposed(semitones),
        event_count=event_count,
    )


def test_the_effective_rate_of_the_reference_key_is_the_stored_rate_itself() -> None:
    assert effective_playback_rate(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY) == REFERENCE_RATE


def test_the_effective_rate_is_a_whole_number_of_hertz() -> None:
    """A semitone above the reference key sounds at 8859.9 Hz, and a rate is countable."""
    assert effective_playback_rate(reference_rate_hz=REFERENCE_RATE, sounded_note=RATE_KEY.transposed(1)) == 8860


def test_a_transposed_occurrence_played_lower_meets_an_untransposed_one_at_the_same_rate() -> None:
    """The tracker fact this whole reading rests on: rate and note only mean something together."""
    transposed = effective_playback_rate(reference_rate_hz=16726, sounded_note=RATE_KEY.transposed(-12))

    assert transposed == effective_playback_rate(reference_rate_hz=8363, sounded_note=RATE_KEY)


def test_usage_meeting_at_one_rate_is_counted_as_one_rate() -> None:
    tally = tally_playback_rates(
        (
            _usage(reference_rate_hz=8363, semitones=0, event_count=3),
            _usage(reference_rate_hz=16726, semitones=-12, event_count=4),
        )
    )

    assert tally == Counter({8363: 7})


def test_playback_rates_are_listed_with_the_most_played_first() -> None:
    tally = tally_playback_rates(
        (
            _usage(reference_rate_hz=8363, semitones=0, event_count=1),
            _usage(reference_rate_hz=8363, semitones=12, event_count=5),
        )
    )

    assert playback_rates_of(tally) == (
        SamplePlaybackRate(rate_hz=16726, event_count=5),
        SamplePlaybackRate(rate_hz=8363, event_count=1),
    )


def test_the_dominant_playback_rate_is_the_one_the_most_events_reach() -> None:
    tally = tally_playback_rates(
        (
            _usage(reference_rate_hz=8363, semitones=0, event_count=1),
            _usage(reference_rate_hz=8363, semitones=12, event_count=5),
        )
    )

    assert dominant_playback_rate(tally) == 16726


def test_a_tied_dominant_playback_rate_resolves_to_the_lower_rate() -> None:
    tally = tally_playback_rates(
        (
            _usage(reference_rate_hz=8363, semitones=0, event_count=2),
            _usage(reference_rate_hz=8363, semitones=12, event_count=2),
        )
    )

    assert dominant_playback_rate(tally) == 8363


def test_a_sample_no_pattern_plays_has_no_dominant_playback_rate() -> None:
    assert dominant_playback_rate(tally_playback_rates(())) is None


def test_the_rate_a_sample_is_played_at_comes_from_its_note_events() -> None:
    assert choose_playback_rate(note_event_rate=16726, occurrence_rates=(8363, 8363)) == 16726


def test_a_sample_no_pattern_plays_falls_back_to_its_dominant_occurrence_rate() -> None:
    assert choose_playback_rate(note_event_rate=None, occurrence_rates=(8363, 22050, 8363)) == 8363


def test_a_sample_with_neither_notes_nor_occurrences_has_no_rate_to_play_at() -> None:
    assert choose_playback_rate(note_event_rate=None, occurrence_rates=()) is None
