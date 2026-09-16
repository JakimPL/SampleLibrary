from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.partials.channels import Channels
from samplemorph.partials.correspondence.assignment import assign_with_fades
from samplemorph.partials.notes import Note
from samplemorph.partials.tracks import CENTS_PER_OCTAVE

CENTS_PER_SEMITONE: Final[float] = CENTS_PER_OCTAVE / SEMITONES_PER_OCTAVE


def note_pairs(first: Channels, second: Channels, *, cap_semitones: float, exponent: float) -> NDArray[np.intp]:
    """Which note of one sound meets which of the other, as index pairs.

    A pair of notes costs what the two carry times how far apart they stand in semitones, raised to
    `exponent`, and a note fades at what it carries times `cap_semitones` raised to the same power, so
    notes further apart than the cap fade instead of meeting. Above the first power the cost of one
    long move outweighs several short ones, which spreads a chord's movement over its voices.
    Shape: the result is ``(pairs, 2)``.
    """
    if first.note_count == 0 or second.note_count == 0:
        return np.zeros((0, 2), dtype=np.intp)

    apart = np.abs(_semitones(first.notes)[:, None] - _semitones(second.notes)) ** exponent
    shares = np.array([note.share for note in first.notes])[:, None] + np.array([note.share for note in second.notes])
    return assign_with_fades(
        0.5 * shares * apart,
        first_fades=0.5 * np.array([note.share for note in first.notes]) * cap_semitones**exponent,
        second_fades=0.5 * np.array([note.share for note in second.notes]) * cap_semitones**exponent,
    )


def harmonic_pairs(first: Channels, second: Channels, *, notes: NDArray[np.intp]) -> NDArray[np.intp]:
    """Which channel meets which once the notes have met: harmonic to harmonic of every pair of notes.

    Shape: the result is ``(pairs, 2)``.
    """
    pairs = [
        (int(here), int(there))
        for first_note, second_note in notes
        for here, there in _same_harmonics(first, second, first_note=int(first_note), second_note=int(second_note))
    ]
    return np.array(pairs, dtype=np.intp).reshape(len(pairs), 2)


def _same_harmonics(first: Channels, second: Channels, *, first_note: int, second_note: int) -> list[tuple[int, int]]:
    here = {int(first.harmonic[index]): int(index) for index in np.flatnonzero(first.note == first_note)}
    there = {int(second.harmonic[index]): int(index) for index in np.flatnonzero(second.note == second_note)}
    return [(here[harmonic], there[harmonic]) for harmonic in sorted(here.keys() & there.keys())]


def _semitones(notes: tuple[Note, ...]) -> NDArray[np.float64]:
    """Where each note stands in semitones, read over the frames it sounds through."""
    return np.array(
        [SEMITONES_PER_OCTAVE * float(np.log2(np.median(note.frequency_hz))) for note in notes], dtype=np.float64
    )
