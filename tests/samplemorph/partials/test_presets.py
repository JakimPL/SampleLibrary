from __future__ import annotations

from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.partials.model import SinusoidalModel
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.partials.conftest import GEOMETRY, RATE_HZ, model_of, times

MIDPOINT: Final[float] = 0.5
JUST_BEFORE: Final[float] = 0.49
CENTS_TOLERANCE: Final[float] = 15.0
LEVEL_TOLERANCE_DB: Final[float] = 1.0
HELD_CEILING_DB: Final[float] = -1.5
PEAK_REACH_HZ: Final[float] = 6.0
HARMONIC_COUNT: Final[int] = 10
C4, E4, G4, F4, A4 = 261.63, 329.63, 392.0, 349.23, 440.0
FIRST_CHORD: Final[tuple[float, ...]] = (C4, E4, G4)
SECOND_CHORD: Final[tuple[float, ...]] = (C4, F4, A4)


def _chord(notes: tuple[float, ...], *, seconds: float = 1.5) -> NDArray[np.float64]:
    seconds_axis = times(seconds)
    total = np.sum(
        [
            np.sin(2.0 * np.pi * harmonic * note * seconds_axis) / harmonic
            for note in notes
            for harmonic in range(1, HARMONIC_COUNT + 1)
        ],
        axis=0,
    )
    chord: NDArray[np.float64] = 0.5 * total / np.abs(total).max()
    return chord


def _level_db(waveform: NDArray[np.float64], frequency_hz: float) -> float:
    """How loud a render stands at one frequency, read over the middle half through the energy of its lobe."""
    middle = waveform[waveform.shape[0] // 4 : 3 * waveform.shape[0] // 4]
    taper = np.hanning(middle.shape[0])
    energy = np.abs(np.fft.rfft(middle * taper)) ** 2
    frequencies = np.fft.rfftfreq(middle.shape[0], 1.0 / RATE_HZ)
    near = np.abs(frequencies - frequency_hz) <= PEAK_REACH_HZ
    scale = middle.shape[0] * float((taper**2).sum())
    return float(20.0 * np.log10(max(2.0 * np.sqrt(energy[near].sum() / scale), 1e-12)))


@pytest.fixture(scope="module")
def chords() -> tuple[SinusoidalModel, SinusoidalModel]:
    return model_of(_chord(FIRST_CHORD)), model_of(_chord(SECOND_CHORD))


def _render(chords: tuple[SinusoidalModel, SinusoidalModel], *, preset: str, weight: float) -> NDArray[np.float64]:
    morph = PartialMorph(profile=PROFILE_PRESETS[preset], geometry=GEOMETRY, settings=TransportSettings())
    return morph.between(chords[0], chords[1], weight=weight)


def _notes_of(waveform: NDArray[np.float64]) -> list[float]:
    return sorted(float(np.median(note.frequency_hz)) for note in model_of(waveform).channels.notes)


def _cents_apart(read_hz: float, true_hz: float) -> float:
    return abs(1200.0 * float(np.log2(read_hz / true_hz)))


def test_a_stepped_middle_is_a_chord_a_keyboard_holds(chords: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    """C stays, E has travelled its semitone to F, and G has travelled half of its two to G sharp."""
    read = _notes_of(_render(chords, preset="stepped", weight=MIDPOINT))

    assert len(read) == 3
    for found, expected in zip(read, sorted((C4, F4, G4 * 2.0 ** (1.0 / 12.0))), strict=True):
        assert _cents_apart(found, expected) <= CENTS_TOLERANCE


def test_a_pivot_holds_what_both_chords_share_and_fades_the_rest_where_it_stands(
    chords: tuple[SinusoidalModel, SinusoidalModel],
) -> None:
    middle = _render(chords, preset="pivot", weight=MIDPOINT)

    first_chord, second_chord = _chord(FIRST_CHORD), _chord(SECOND_CHORD)
    assert abs(_level_db(middle, C4) - _level_db(first_chord, C4)) <= LEVEL_TOLERANCE_DB
    for note, chord in ((E4, first_chord), (G4, first_chord), (F4, second_chord), (A4, second_chord)):
        assert _level_db(middle, note) - _level_db(chord, note) <= HELD_CEILING_DB


def test_a_switch_keeps_the_first_chord_until_the_middle(chords: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    read = _notes_of(_render(chords, preset="switch", weight=JUST_BEFORE))

    assert len(read) == 3
    for found, expected in zip(read, sorted(FIRST_CHORD), strict=True):
        assert _cents_apart(found, expected) <= CENTS_TOLERANCE


def test_a_crossfade_middle_holds_both_chords_at_once(chords: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    middle = _render(chords, preset="crossfade", weight=MIDPOINT)

    first_chord, second_chord = _chord(FIRST_CHORD), _chord(SECOND_CHORD)
    for note, chord in ((E4, first_chord), (G4, first_chord), (F4, second_chord), (A4, second_chord)):
        assert abs(_level_db(middle, note) - _level_db(chord, note) + 3.0) <= LEVEL_TOLERANCE_DB


@pytest.mark.parametrize("preset", tuple(PROFILE_PRESETS))
def test_every_preset_renders_the_same_two_ends(preset: str, chords: tuple[SinusoidalModel, SinusoidalModel]) -> None:
    """A profile says what the middle is, and both ends are the sounds themselves whichever middle is chosen."""
    for weight in (0.0, 1.0):
        assert np.array_equal(
            _render(chords, preset=preset, weight=weight), _render(chords, preset="glide", weight=weight)
        )
