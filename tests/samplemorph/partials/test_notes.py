from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.notes import estimate_notes
from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import CENTS_PER_OCTAVE
from tests.samplemorph.partials.conftest import RATE_HZ, harmonics, times, tracks_of

SETTINGS: Final[NoteSettings] = NoteSettings()
CENTS_TOLERANCE: Final[float] = 5.0
HARMONIC_COUNT: Final[int] = 8
PIANO_INHARMONICITY: Final[float] = 4e-4
PIANO_HARMONICS: Final[int] = 20
PIANO_SHARE_FLOOR: Final[float] = 0.9
INHARMONICITY_TOLERANCE: Final[float] = 1e-4
BAR_RATIOS: Final[tuple[float, ...]] = (1.0, 2.756, 5.404, 8.933, 13.34)
C4, E4, G4 = 261.63, 329.63, 392.0


def _notes_of(waveform: NDArray[np.float64], *, settings: NoteSettings = SETTINGS) -> tuple[float, ...]:
    notes = estimate_notes(tracks_of(waveform), settings=settings)
    return tuple(float(np.median(note.frequency_hz)) for note in notes)


def _cents_apart(read_hz: float, true_hz: float) -> float:
    return abs(CENTS_PER_OCTAVE * float(np.log2(read_hz / true_hz)))


def _stretched(fundamental_hz: float, *, harmonic_count: int, inharmonicity: float) -> NDArray[np.float64]:
    seconds = times()
    stretch = [np.sqrt(1.0 + inharmonicity * harmonic**2) for harmonic in range(1, harmonic_count + 1)]
    tone = np.sum(
        [
            np.sin(2.0 * np.pi * fundamental_hz * harmonic * stretch[harmonic - 1] * seconds) / harmonic
            for harmonic in range(1, harmonic_count + 1)
        ],
        axis=0,
    )
    scaled: NDArray[np.float64] = 0.5 * tone / np.abs(tone).max()
    return scaled


def _inharmonic(fundamental_hz: float, ratios: tuple[float, ...]) -> NDArray[np.float64]:
    seconds = times()
    tone = np.sum([np.sin(2.0 * np.pi * fundamental_hz * ratio * seconds) for ratio in ratios], axis=0)
    struck: NDArray[np.float64] = 0.5 * tone / np.abs(tone).max()
    return struck


def test_a_tone_is_one_note_at_its_own_pitch() -> None:
    read = _notes_of(harmonics(220.0, harmonic_count=HARMONIC_COUNT))

    assert len(read) == 1
    assert _cents_apart(read[0], 220.0) <= CENTS_TOLERANCE


def test_a_tone_whose_fundamental_is_missing_keeps_its_own_pitch() -> None:
    """Every partial of the tone is a harmonic of the note under them, and nothing stands between them."""
    seconds = times()
    tone = np.sum([np.sin(2.0 * np.pi * 220.0 * harmonic * seconds) / harmonic for harmonic in range(2, 9)], axis=0)

    read = _notes_of(0.5 * tone / np.abs(tone).max())

    assert len(read) == 1
    assert _cents_apart(read[0], 220.0) <= CENTS_TOLERANCE


def test_a_chord_is_read_note_by_note() -> None:
    chord = sum(harmonics(note, harmonic_count=HARMONIC_COUNT) for note in (C4, E4, G4)) / 3.0

    read = sorted(_notes_of(chord))

    assert len(read) == 3
    for found, played in zip(read, (C4, E4, G4), strict=True):
        assert _cents_apart(found, played) <= CENTS_TOLERANCE


def test_a_stiff_string_is_one_note_holding_nearly_all_of_it() -> None:
    piano = _stretched(110.0, harmonic_count=PIANO_HARMONICS, inharmonicity=PIANO_INHARMONICITY)

    notes = estimate_notes(tracks_of(piano), settings=SETTINGS)

    assert len(notes) == 1
    assert _cents_apart(float(np.median(notes[0].frequency_hz)), 110.0) <= CENTS_TOLERANCE
    assert abs(notes[0].inharmonicity - PIANO_INHARMONICITY) <= INHARMONICITY_TOLERANCE
    assert notes[0].share >= PIANO_SHARE_FLOOR


def test_a_struck_bar_leaves_its_partials_free_of_any_note() -> None:
    """A bar's partials stand at ratios no harmonic series runs through, so none of them reads as a note."""
    assert _notes_of(_inharmonic(300.0, BAR_RATIOS)) == ()


def test_two_notes_a_fifth_apart_share_the_partials_between_them() -> None:
    """The fifth's even harmonics are the lower note's thirds and sixths, and both notes sound them."""
    chord = (harmonics(C4, harmonic_count=HARMONIC_COUNT) + harmonics(G4, harmonic_count=HARMONIC_COUNT)) / 2.0

    notes = estimate_notes(tracks_of(chord), settings=SETTINGS)

    assert len(notes) == 2
    shared = set(notes[0].partials.tolist()) & set(notes[1].partials.tolist())
    assert shared


def test_settings_refuse_a_note_of_no_harmonics() -> None:
    with pytest.raises(ValueError):
        NoteSettings(smallest_note_harmonics=0)


def test_the_frequency_of_a_note_follows_a_vibrato_every_harmonic_shares() -> None:
    """A note's pitch is read through all its harmonics at once, so what they share stays and their jitter cancels."""
    depth_cents, rate_hz = 40.0, 5.0
    seconds = times()
    frequency = 220.0 * 2.0 ** (depth_cents / CENTS_PER_OCTAVE * np.sin(2.0 * np.pi * rate_hz * seconds))
    phase = 2.0 * np.pi * np.cumsum(frequency) / RATE_HZ
    tone = np.sum([np.sin(harmonic * phase) / harmonic for harmonic in range(1, HARMONIC_COUNT + 1)], axis=0)

    notes = estimate_notes(tracks_of(0.5 * tone / np.abs(tone).max()), settings=SETTINGS)

    assert len(notes) == 1
    read = CENTS_PER_OCTAVE * np.log2(notes[0].frequency_hz / 220.0)
    inner = slice(read.shape[0] // 4, 3 * read.shape[0] // 4)
    truth = depth_cents * np.sin(2.0 * np.pi * rate_hz * np.arange(read.shape[0]) * 128.0 / RATE_HZ)
    assert float(np.corrcoef(read[inner], truth[inner])[0, 1]) >= 0.95
