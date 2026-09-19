from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from samplemorph.partials.notes import estimate_notes
from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import PartialTracks


@dataclass(frozen=True)
class NoteReading:
    """How a sound's partials read as notes: how many notes it sounds, and how much of its partial energy stands on them.

    `harmonicity` reads near one for a chord of clean notes, near zero for a sound of scattered
    partials, and somewhere between for a morph whose partials have drifted off their own series:
    it says whether what a point holds still sounds like notes. `note_count` says how many: a morph
    between two notes that glides holds one, and one that crossfades holds both in its middle. A
    sound holding no partial sounds no note and its harmonicity is not a number.
    """

    note_count: int
    harmonicity: float


def note_reading(tracks: PartialTracks, *, settings: NoteSettings) -> NoteReading:
    """Read a sound's partials as notes once, for both how many there are and how much of the sound they hold."""
    energy = (tracks.amplitude.astype(np.float64) ** 2).sum(axis=1)
    total = float(energy.sum())
    if tracks.track_count == 0 or total <= 0.0:
        return NoteReading(note_count=0, harmonicity=float("nan"))

    notes = estimate_notes(tracks, settings=settings)
    sounded = np.zeros(tracks.track_count, dtype=bool)
    for note in notes:
        sounded[note.partials] = True
    return NoteReading(note_count=len(notes), harmonicity=float(energy[sounded].sum() / total))
