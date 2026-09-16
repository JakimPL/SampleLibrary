from __future__ import annotations

import math
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.measurement.morph_path.harmonicity import harmonicity
from samplemorph.measurement.morph_path.heard_partials import heard_partials
from samplemorph.partials.settings import NoteSettings
from tests.samplemorph.partials.conftest import RATE_HZ, harmonics, times

SETTINGS: Final[NoteSettings] = NoteSettings()
NOTES_FLOOR: Final[float] = 0.9
SCATTERED_CEILING: Final[float] = 0.5
BAR_RATIOS: Final[tuple[float, ...]] = (1.0, 2.756, 5.404, 8.933, 13.34)
C4, E4, G4 = 261.63, 329.63, 392.0


def _read(waveform: NDArray[np.float64]) -> float:
    return harmonicity(heard_partials(waveform, rate_hz=RATE_HZ), settings=SETTINGS)


def test_a_chord_stands_on_its_notes() -> None:
    chord = sum(harmonics(note, harmonic_count=8) for note in (C4, E4, G4)) / 3.0

    assert _read(np.asarray(chord)) >= NOTES_FLOOR


def test_a_struck_bar_stands_on_partials_of_its_own() -> None:
    seconds = times()
    struck = np.sum([np.sin(2.0 * np.pi * 300.0 * ratio * seconds) for ratio in BAR_RATIOS], axis=0)

    assert _read(0.5 * struck / np.abs(struck).max()) <= SCATTERED_CEILING


def test_a_sound_holding_no_partial_reads_no_number() -> None:
    assert math.isnan(_read(np.random.default_rng(8).normal(size=times().shape[0])))
