from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks
from samplemorph.partials.voices import PartialVoices, partial_voices

STRETCH_GRID_STEPS: Final[int] = 8
REFINING_GRID_STEPS: Final[int] = 64
CANDIDATE_CENTS_STEP: Final[float] = 1.0
DEEPENING_DIVISORS: Final[tuple[int, ...]] = (2, 3)
CONSECUTIVE_SHARE: Final[float] = 0.85
SALIENCE_OFFSET_HZ: Final[float] = 52.0
SALIENCE_SCALE_HZ: Final[float] = 320.0
SPACING_SHARE: Final[float] = 1.0 / 3.0


def stretch_of(harmonics: NDArray[np.intp], *, inharmonicity: float) -> NDArray[np.float64]:
    """How much further out than a whole multiple each harmonic of a stiff string stands."""
    stretched: NDArray[np.float64] = np.sqrt(1.0 + inharmonicity * harmonics.astype(np.float64) ** 2)
    return stretched


@dataclass(frozen=True)
class Note:
    """One note a sound holds: where its fundamental stands over time, how far its harmonics stretch, and which partial sounds each.

    Harmonic `k` sounds at ``k * frequency_hz * stretch(k)``, the stretch a stiff string's, so a
    piano's upper partials stand where the string puts them. `partials` names the track sounding each
    harmonic of `harmonics`, and `share` is the part of the sound's partial energy the note carries,
    a partial two notes share counted in both. Shape: `frequency_hz` is ``(frames,)``.
    """

    frequency_hz: NDArray[np.float64]
    inharmonicity: float
    harmonics: NDArray[np.intp]
    partials: NDArray[np.intp]
    share: float

    @property
    def harmonic_count(self) -> int:
        return int(self.harmonics.shape[0])

    def harmonic_frequency_hz(self, harmonics: NDArray[np.intp]) -> NDArray[np.float64]:
        """Where each of these harmonics of the note sounds, frame by frame. Shape: ``(harmonics, frames)``."""
        multiples = harmonics.astype(np.float64) * stretch_of(harmonics, inharmonicity=self.inharmonicity)
        frequency: NDArray[np.float64] = multiples[:, None] * self.frequency_hz
        return frequency


def estimate_notes(tracks: PartialTracks, *, settings: NoteSettings) -> tuple[Note, ...]:
    """Read a sound's partials as notes, the loudest note first.

    A note is proposed from every partial taken as a harmonic of it, and what a proposal is worth is
    the loudness of the partials it sounds, each weighed down the further up the series it lies, so
    the notes a listener hears outweigh the fundamental a chord sits over. A proposal has to sound
    through enough of the harmonics between its lowest and its highest to read as one string; where
    the note under it sounds the partials in between as one unbroken series, that deeper note stands
    instead, which is how a tone whose fundamental is quiet keeps its own pitch. The note found takes
    its partials, a partial it shares with a note already read counted in both, and the search runs
    again on what is left. Each note's fundamental is then followed over time through every harmonic
    sounding it, so measurement jitter cancels while a vibrato the whole note shares stays.
    """
    voices = partial_voices(tracks)
    if voices.count == 0:
        return ()

    notes: list[Note] = []
    taken = np.zeros(voices.count, dtype=bool)
    while len(notes) < settings.largest_note_count:
        found = _best_reading(voices, taken=taken, settings=settings)
        if found is None or found.fresh < settings.note_share_floor:
            break
        notes.append(_followed(found, tracks=tracks))
        taken[found.partials] = True
    return tuple(notes)


@dataclass(frozen=True)
class _Reading:
    """One note as the search reads it: where it stands, how it stretches, and what it sounds through.

    `share` is the energy of every partial it sounds, and `fresh` the energy of those no note has
    claimed yet, which is what the note adds to the reading of the sound.
    """

    cents: float
    inharmonicity: float
    harmonics: NDArray[np.intp]
    partials: NDArray[np.intp]
    share: float
    fresh: float

    @property
    def runs_consecutively(self) -> bool:
        """Whether the note sounds through nearly every harmonic between the lowest and the highest it holds."""
        span = int(self.harmonics.max()) - int(self.harmonics.min()) + 1
        return bool(self.harmonics.shape[0] >= CONSECUTIVE_SHARE * span)


@dataclass(frozen=True)
class _Search:
    """What one pass of the search reads against: a sound's partials, those already read, and the settings it follows."""

    voices: PartialVoices
    taken: NDArray[np.bool_]
    harmonics: NDArray[np.intp]
    settings: NoteSettings

    @property
    def loudness(self) -> NDArray[np.float64]:
        """What every partial is worth to a note, zero for those a note already sounds. Shape: ``(partials,)``."""
        worth: NDArray[np.float64] = np.where(self.taken, 0.0, 1.0) * self.voices.loudness
        return worth


@dataclass(frozen=True)
class _Sieve:
    """The harmonic series candidates propose, read against a sound's partials.

    Shapes: `partials` and `matched` are ``(candidates, harmonics)``, and `score` ``(candidates,)``.
    """

    partials: NDArray[np.intp]
    matched: NDArray[np.bool_]
    score: NDArray[np.float64]


def _best_reading(voices: PartialVoices, *, taken: NDArray[np.bool_], settings: NoteSettings) -> _Reading | None:
    """The best note the partials hold beyond those already read, refined on the partials it sounds."""
    if bool(taken.all()):
        return None

    search = _Search(
        voices=voices,
        taken=taken,
        harmonics=np.arange(1, settings.harmonic_count + 1, dtype=np.intp),
        settings=settings,
    )
    candidates = _candidates(search)
    if candidates.size == 0:
        return None

    found = _loudest(candidates, search)
    if found is None:
        return None

    reading = _read_one(found[0], search, inharmonicity=found[1])
    if reading is None:
        return None
    return _refined(_deepened(reading, search), voices, settings=settings)


def _loudest(candidates: NDArray[np.float64], search: _Search) -> tuple[float, float] | None:
    """The candidate and the stretch that together sound the loudest set of partials."""
    best: tuple[float, float] | None = None
    loudest = 0.0
    for inharmonicity in _stretch_grid(search.settings):
        sieve = _sift(candidates, search, inharmonicity=inharmonicity)
        found = int(np.argmax(sieve.score))
        if float(sieve.score[found]) > loudest:
            loudest = float(sieve.score[found])
            best = (float(candidates[found]), float(inharmonicity))
    return best


def _candidates(search: _Search) -> NDArray[np.float64]:
    """Every fundamental the partials left over propose, each of them taken as every harmonic in turn."""
    proposed = (search.voices.cents[~search.taken][:, None] - CENTS_PER_OCTAVE * np.log2(search.harmonics)).ravel()
    lowest = CENTS_PER_OCTAVE * np.log2(search.settings.lowest_note_hz)
    within = proposed[proposed >= lowest]
    return np.unique(np.round(within / CANDIDATE_CENTS_STEP) * CANDIDATE_CENTS_STEP)


def _stretch_grid(settings: NoteSettings) -> NDArray[np.float64]:
    """The inharmonicities the search tries, spread finely where a string is nearly ideal."""
    grid: NDArray[np.float64] = np.linspace(0.0, np.sqrt(settings.largest_inharmonicity), STRETCH_GRID_STEPS + 1) ** 2
    return grid


def _sift(candidates: NDArray[np.float64], search: _Search, *, inharmonicity: float) -> _Sieve:
    """Which partial sounds each harmonic of every candidate, and what the partials it adds are worth.

    A partial another note already sounds still stands as a harmonic here, since two notes a fifth
    apart share every other partial, and what a candidate is worth is what it adds: the salience of
    the partials no note has claimed yet. A candidate sounding too few harmonics, or too few of those
    it reaches across, is worth nothing.
    """
    harmonics = search.harmonics
    stretch = CENTS_PER_OCTAVE * np.log2(harmonics * stretch_of(harmonics, inharmonicity=inharmonicity))
    targets = candidates[:, None] + stretch
    order = np.argsort(search.voices.cents)
    found, distance = _nearest(targets, cents=search.voices.cents[order])
    matched = distance <= _tolerances(harmonics, settings=search.settings)
    salience = _salience(candidates, frequency_hz=search.voices.frequency_hz[order], loudness=search.loudness[order])
    worth = np.take_along_axis(salience, found, axis=1) * matched
    return _Sieve(
        partials=order[found],
        matched=matched,
        score=np.where(_stands(matched, settings=search.settings), worth, 0.0).sum(axis=1),
    )


def _stands(matched: NDArray[np.bool_], *, settings: NoteSettings) -> NDArray[np.bool_]:
    """Which candidates sound through enough harmonics, and through enough of those they reach across."""
    count = matched.sum(axis=1)
    reach = np.arange(matched.shape[1])
    lowest = np.where(matched, reach, matched.shape[1]).min(axis=1)
    highest = np.where(matched, reach, -1).max(axis=1)
    dense = count >= settings.note_density * (highest - lowest + 1)
    stands: NDArray[np.bool_] = (count >= settings.smallest_note_harmonics) & dense
    return stands[:, None]


def _read_one(candidate: float, search: _Search, *, inharmonicity: float) -> _Reading | None:
    """One candidate read in full: the harmonics it sounds, the partials sounding them, and what it carries."""
    sieve = _sift(np.array([candidate]), search, inharmonicity=inharmonicity)
    if sieve.score[0] <= 0.0:
        return None

    matched = sieve.matched[0]
    partials = sieve.partials[0][matched]
    return _Reading(
        cents=candidate,
        inharmonicity=inharmonicity,
        harmonics=search.harmonics[matched],
        partials=partials,
        share=float(search.voices.share[partials].sum()),
        fresh=float(search.voices.share[partials][~search.taken[partials]].sum()),
    )


def _deepened(reading: _Reading, search: _Search) -> _Reading:
    """The note an octave or a twelfth under this one, where that one sounds the same partials and more of them.

    A tone whose fundamental is quiet reads first as the note its second harmonic makes, and the note
    under it sounds the partials in between; a chord reads as the fundamental a triad sits over, and
    that one leaves gaps in its own series, so a deeper note stands only where its harmonics run one
    after another from the lowest it sounds to the highest.
    """
    deepest = reading
    for divisor in DEEPENING_DIVISORS:
        under = _read_one(
            deepest.cents - CENTS_PER_OCTAVE * np.log2(divisor), search, inharmonicity=deepest.inharmonicity
        )
        if under is not None and under.share > deepest.share and under.runs_consecutively:
            deepest = under
    return deepest


def _tolerances(harmonics: NDArray[np.intp], *, settings: NoteSettings) -> NDArray[np.float64]:
    """How far a partial may stand from each harmonic, a share of the gap to the harmonic above it."""
    spacing = CENTS_PER_OCTAVE * np.log2((harmonics + 1) / harmonics)
    tolerance: NDArray[np.float64] = np.minimum(settings.harmonic_cents, SPACING_SHARE * spacing)
    return tolerance


def _salience(
    candidates: NDArray[np.float64], *, frequency_hz: NDArray[np.float64], loudness: NDArray[np.float64]
) -> NDArray[np.float64]:
    """What every partial is worth to every candidate: its loudness, weighed down the further up the series it lies.

    A partial counts for a candidate under it in proportion to ``(f0 + offset) / (f + scale)``
    (Klapuri, 2006), so the partials a note is heard by carry it, and a fundamental far below stands
    on weights small enough to leave the notes themselves the louder reading. Shape: the result is
    ``(candidates, partials)``.
    """
    fundamental = 2.0 ** (candidates / CENTS_PER_OCTAVE)
    weight = (fundamental[:, None] + SALIENCE_OFFSET_HZ) / (frequency_hz + SALIENCE_SCALE_HZ)
    worth: NDArray[np.float64] = weight * loudness
    return worth


def _nearest(
    targets: NDArray[np.float64], *, cents: NDArray[np.float64]
) -> tuple[NDArray[np.intp], NDArray[np.float64]]:
    """The nearest of `cents` to every target, as an index into those sorted cents and the distance to it."""
    index = np.searchsorted(cents, targets)
    below = np.clip(index - 1, 0, cents.shape[0] - 1)
    above = np.clip(index, 0, cents.shape[0] - 1)
    found = np.where(np.abs(cents[above] - targets) < np.abs(cents[below] - targets), above, below)
    return found.astype(np.intp), np.abs(cents[found] - targets)


def _refined(reading: _Reading, voices: PartialVoices, *, settings: NoteSettings) -> _Reading:
    """The same note with its fundamental and its stretch read off the partials it sounds."""
    harmonics = reading.harmonics.astype(np.float64)
    cents = voices.cents[reading.partials]
    weights = voices.share[reading.partials]
    best, smallest = reading, np.inf
    for inharmonicity in np.linspace(0.0, settings.largest_inharmonicity, REFINING_GRID_STEPS + 1):
        stretch = CENTS_PER_OCTAVE * np.log2(harmonics * stretch_of(reading.harmonics, inharmonicity=inharmonicity))
        fundamental = float(np.average(cents - stretch, weights=weights))
        residual = float(np.average((cents - stretch - fundamental) ** 2, weights=weights))
        if residual < smallest:
            smallest = residual
            best = _Reading(
                cents=fundamental,
                inharmonicity=float(inharmonicity),
                harmonics=reading.harmonics,
                partials=reading.partials,
                share=reading.share,
                fresh=reading.fresh,
            )
    return best


def _followed(reading: _Reading, *, tracks: PartialTracks) -> Note:
    """A note's fundamental over time, read through every harmonic sounding it at each frame."""
    multiples = reading.harmonics.astype(np.float64) * stretch_of(
        reading.harmonics, inharmonicity=reading.inharmonicity
    )
    sounded = tracks.frequency_hz[reading.partials].astype(np.float64) / multiples[:, None]
    loudness = tracks.amplitude[reading.partials].astype(np.float64) ** 2
    weights = np.where(loudness.sum(axis=0) > 0.0, loudness, 1.0)
    return Note(
        frequency_hz=np.exp((weights * np.log(sounded)).sum(axis=0) / weights.sum(axis=0)),
        inharmonicity=reading.inharmonicity,
        harmonics=reading.harmonics,
        partials=reading.partials,
        share=reading.share,
    )
