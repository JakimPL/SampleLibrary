from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.notes import Note, estimate_notes
from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import PartialTracks
from samplemorph.partials.voices import partial_voices

FREE_PARTIAL: Final[int] = -1
QUIET_LOUDNESS: Final[float] = 1e-12


@dataclass(frozen=True)
class Channels:
    """Every line a sound sounds along: each note's harmonics, and the partials standing free of any note.

    A harmonic channel follows its note's fundamental, so a vibrato every harmonic of a note shares
    stays one movement; a free channel follows the partial it was read from. `note` names the note a
    channel belongs to and `harmonic` which harmonic of it, both `FREE_PARTIAL` and 0 for a partial
    of its own. Shapes: `note` and `harmonic` are ``(channels,)`` beside `tracks`.
    """

    tracks: PartialTracks
    note: NDArray[np.intp]
    harmonic: NDArray[np.intp]
    notes: tuple[Note, ...]

    @property
    def channel_count(self) -> int:
        return self.tracks.track_count

    @property
    def frame_count(self) -> int:
        return self.tracks.frame_count

    @property
    def note_count(self) -> int:
        return len(self.notes)


def channelize(tracks: PartialTracks, *, settings: NoteSettings) -> Channels:
    """Read a sound's partials as the lines it sounds along.

    Every harmonic a note sounds becomes a channel of that note, standing where the note's own
    fundamental puts it, and a partial two notes share is split between them by what each note's
    other harmonics predict it to be, so the two halves sum to the partial as measured. Every partial
    no note sounds stays a line of its own.
    """
    notes = estimate_notes(tracks, settings=settings)
    if not notes:
        return Channels(
            tracks=tracks,
            note=np.full(tracks.track_count, FREE_PARTIAL, dtype=np.intp),
            harmonic=np.zeros(tracks.track_count, dtype=np.intp),
            notes=(),
        )

    shares = _shares(notes, tracks=tracks)
    frequency = [note.harmonic_frequency_hz(note.harmonics) for note in notes]
    amplitude = [tracks.amplitude[note.partials] * shares[index][:, None] for index, note in enumerate(notes)]
    free = _free_partials(notes, count=tracks.track_count)
    return Channels(
        tracks=PartialTracks(
            frequency_hz=np.concatenate([*frequency, tracks.frequency_hz[free]]).astype(np.float32),
            amplitude=np.concatenate([*amplitude, tracks.amplitude[free]]).astype(np.float32),
            hop_length=tracks.hop_length,
            rate_hz=tracks.rate_hz,
        ),
        note=np.concatenate(
            [np.full(note.harmonic_count, index, dtype=np.intp) for index, note in enumerate(notes)]
            + [np.full(free.shape[0], FREE_PARTIAL, dtype=np.intp)]
        ),
        harmonic=np.concatenate([note.harmonics for note in notes] + [np.zeros(free.shape[0], dtype=np.intp)]).astype(
            np.intp
        ),
        notes=notes,
    )


def _free_partials(notes: tuple[Note, ...], *, count: int) -> NDArray[np.intp]:
    """Every partial no note sounds."""
    sounded = np.zeros(count, dtype=bool)
    for note in notes:
        sounded[note.partials] = True
    return np.flatnonzero(~sounded).astype(np.intp)


def _shares(notes: tuple[Note, ...], *, tracks: PartialTracks) -> list[NDArray[np.float64]]:
    """How much of each partial every note that sounds it takes, the shares of one partial summing to all of it.

    A partial two notes share is split by what each note's own harmonics predict it to hold, read
    from the envelope its unshared harmonics draw, so the louder note over that stretch of the
    spectrum takes the larger part of it.
    """
    loudness = partial_voices(tracks).loudness
    claims = np.zeros(tracks.track_count)
    for note in notes:
        claims[note.partials] += 1.0
    predicted = [_predicted(note, loudness=loudness, claims=claims) for note in notes]
    totals = np.zeros(tracks.track_count)
    for note, prediction in zip(notes, predicted, strict=True):
        totals[note.partials] += prediction
    return [
        np.where(
            totals[note.partials] > 0.0,
            prediction / np.where(totals[note.partials] > 0.0, totals[note.partials], 1.0),
            1.0 / claims[note.partials],
        )
        for note, prediction in zip(notes, predicted, strict=True)
    ]


def _predicted(note: Note, *, loudness: NDArray[np.float64], claims: NDArray[np.float64]) -> NDArray[np.float64]:
    """How loud each harmonic of a note stands by the envelope its unshared harmonics draw."""
    alone = claims[note.partials] <= 1.0
    measured = np.maximum(loudness[note.partials], QUIET_LOUDNESS)
    if not alone.any():
        return measured

    reach = np.log(note.harmonics.astype(np.float64))
    drawn: NDArray[np.float64] = np.exp(np.interp(reach, reach[alone], np.log(measured[alone])))
    return np.where(alone, measured, drawn)
