from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.fate import fate_groups
from samplemorph.partials.notes import Note, estimate_notes
from samplemorph.partials.places import partial_places
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks

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
    fate: NDArray[np.intp]
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

    @property
    def units(self) -> NDArray[np.intp]:
        """The object each channel travels as: a whole note, or the partials standing free that share a fate.

        A note holds its harmonics together, which is what harmonicity is good for, and the partials
        no note sounds are held together by the shape they rise and fall in, which is what groups the
        partials of a bell or a drum that no series explains. Shape: the result is ``(channels,)``.
        """
        together = np.where(self.note >= 0, self.note, self.note_count + self.fate)
        _, drawn = np.unique(together, return_inverse=True)
        return drawn.astype(np.intp)

    @property
    def lines(self) -> NDArray[np.intp]:
        """Which line each channel travels on: the note it is a harmonic of, or one of its own where it stands free.

        Shape: the result is ``(channels,)``.
        """
        own: NDArray[np.intp] = np.where(
            self.note >= 0, self.note, self.note_count + np.arange(self.channel_count)
        ).astype(np.intp)
        return own


def channelize(tracks: PartialTracks, *, settings: PartialSettings) -> Channels:
    """Read a sound's partials as the lines it sounds along.

    Every harmonic between the lowest and the highest a note sounds becomes a channel of that note,
    standing where the note's own fundamental puts it and silent where no partial sounds it, so two
    notes that meet travel harmonic by harmonic over the whole of their range. A partial two notes
    share is split between them by what each note's other harmonics predict it to be, so the two
    halves sum to the partial as measured, and every partial no note sounds stays a line of its own.
    Each channel is then given the object it rises and falls with, which is what lets a whole set of
    them travel as one.
    """
    notes = estimate_notes(tracks, settings=settings.notes)
    if not notes:
        return Channels(
            tracks=tracks,
            note=np.full(tracks.track_count, FREE_PARTIAL, dtype=np.intp),
            fate=fate_groups(tracks, settings=settings.fate),
            harmonic=np.zeros(tracks.track_count, dtype=np.intp),
            notes=(),
        )

    shares = _shares(notes, tracks=tracks)
    sounding = [_sounding(note) for note in notes]
    frequency = [note.harmonic_frequency_hz(sounding[index]) for index, note in enumerate(notes)]
    amplitude = [
        _over_harmonics(note, sounding=sounding[index], amplitude=tracks.amplitude, share=shares[index])
        for index, note in enumerate(notes)
    ]
    free = _free_partials(notes, count=tracks.track_count)
    channels = PartialTracks(
        frequency_hz=np.concatenate([*frequency, tracks.frequency_hz[free]]).astype(np.float32),
        amplitude=np.concatenate([*amplitude, tracks.amplitude[free]]).astype(np.float32),
        hop_length=tracks.hop_length,
        rate_hz=tracks.rate_hz,
    )
    return Channels(
        tracks=channels,
        note=np.concatenate(
            [np.full(sounding[index].shape[0], index, dtype=np.intp) for index in range(len(notes))]
            + [np.full(free.shape[0], FREE_PARTIAL, dtype=np.intp)]
        ),
        harmonic=np.concatenate([*sounding, np.zeros(free.shape[0], dtype=np.intp)]).astype(np.intp),
        fate=fate_groups(channels, settings=settings.fate),
        notes=notes,
    )


def _sounding(note: Note) -> NDArray[np.intp]:
    """Every harmonic between the lowest and the highest a note sounds, the silent ones among them."""
    return np.arange(int(note.harmonics.min()), int(note.harmonics.max()) + 1, dtype=np.intp)


def _over_harmonics(
    note: Note, *, sounding: NDArray[np.intp], amplitude: NDArray[np.float32], share: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Each harmonic's amplitude over time, silence where no partial sounds it.

    Two tracks standing on one harmonic are one partial followed twice, so their amplitudes add into
    the one channel that harmonic gets. Shape: the result is ``(harmonics, frames)``.
    """
    over = np.zeros((sounding.shape[0], amplitude.shape[1]))
    where = np.searchsorted(sounding, note.harmonics)
    np.add.at(over, where, amplitude[note.partials] * share[:, None])
    return over


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
    loudness = partial_places(tracks).loudness
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
