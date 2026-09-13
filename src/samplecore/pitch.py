from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable

from trackmod.core.notes.pitch import Note
from trackmod.schema.scalars import Rate
from trackmod.spec.pitch import NOTES_PER_OCTAVE, RATE_NOTE

from samplecore.models.note_event import SampleNoteUsage, SamplePlaybackRate
from samplecore.naming import choose_dominant_rate


def sounding_rate_hz(*, reference_rate_hz: Rate, sounded_note: Note) -> float:
    """The rate a sample's frames are read at to sound one note.

    An occurrence's stored rate is a reference: the speed the waveform plays at when the key every
    tracker counts its tuning from -- C-5 -- is pressed. Every other note moves that rate by the
    equal-tempered ratio between the two, which is what makes a note, rather than a rate, the thing a
    sample is actually played at.
    """
    # math.pow rather than `**`: typeshed types float exponentiation as returning Any, since a
    # negative base and a fractional exponent give a complex number.
    return reference_rate_hz * math.pow(2.0, (sounded_note.value - RATE_NOTE) / NOTES_PER_OCTAVE)


def effective_playback_rate(*, reference_rate_hz: Rate, sounded_note: Note) -> Rate:
    """The whole-hertz rate one note event really reads a sample's frames at.

    Tracker rates are whole numbers and a fraction of a hertz sits far below hearing, so rounding
    keeps the rates a sample is played at countable: every note event that sounds the same pitch
    lands on one value, whichever occurrence rate and key it arrived through.
    """
    return round(sounding_rate_hz(reference_rate_hz=reference_rate_hz, sounded_note=sounded_note))


def tally_playback_rates(usages: Iterable[SampleNoteUsage]) -> Counter[Rate]:
    """Fold one sample's note usage onto the effective rates it is heard at, with their event counts.

    An occurrence rate and a pressed key each mean nothing alone, and several pairs meet at the same
    speed -- a waveform transposed down an octave and played an octave higher sounds exactly as the
    untransposed one does -- so their events belong to one rate and are counted as one.
    """
    tally: Counter[Rate] = Counter()
    for usage in usages:
        rate_hz = effective_playback_rate(reference_rate_hz=usage.reference_rate_hz, sounded_note=usage.sounded_note)
        tally[rate_hz] += usage.event_count

    return tally


def playback_rates_of(tally: Counter[Rate]) -> tuple[SamplePlaybackRate, ...]:
    """Every effective rate a sample is heard at, the most played first, ties by ascending rate."""
    return tuple(
        SamplePlaybackRate(rate_hz=rate_hz, event_count=event_count)
        for rate_hz, event_count in sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    )


def dominant_playback_rate(tally: Counter[Rate]) -> Rate | None:
    """The effective rate a sample is heard at most often, ties going to the lower rate.

    Mirrors `samplecore.naming.choose_dominant_rate`'s rule, so the rate chosen from note events and
    the rate chosen from occurrences are chosen the same way. `None` for a sample no pattern plays.
    """
    rates = playback_rates_of(tally)
    return rates[0].rate_hz if rates else None


def choose_playback_rate(*, note_event_rate: Rate | None, occurrence_rates: Iterable[Rate]) -> Rate | None:
    """The rate to play one sample at, from what the library is known to do with it.

    The rate its note events settle on is the one the library really sounds it at. Where no pattern
    reaches it, its occurrences' own dominant rate is what a module declares the waveform plays at,
    which is the closest reading left. `None` for a sample with neither.
    """
    return note_event_rate if note_event_rate is not None else choose_dominant_rate(occurrence_rates)
