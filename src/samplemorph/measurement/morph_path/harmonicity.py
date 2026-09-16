from __future__ import annotations

import numpy as np

from samplemorph.partials.notes import estimate_notes
from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import PartialTracks


def harmonicity(tracks: PartialTracks, *, settings: NoteSettings) -> float:
    """How much of a sound's partial energy stands on the harmonics of notes.

    A chord of clean notes reads near one, a sound of scattered partials near zero, and a morph whose
    partials have drifted off their own series somewhere between: it says whether what a point holds
    still sounds like notes. A sound holding no partial reads not a number.
    """
    if tracks.track_count == 0:
        return float("nan")

    energy = (tracks.amplitude.astype(np.float64) ** 2).sum(axis=1)
    total = float(energy.sum())
    if total <= 0.0:
        return float("nan")

    sounded = np.zeros(tracks.track_count, dtype=bool)
    for note in estimate_notes(tracks, settings=settings):
        sounded[note.partials] = True
    return float(energy[sounded].sum() / total)
