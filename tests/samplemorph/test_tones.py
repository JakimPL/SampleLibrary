from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.tones import HarmonicTone, harmonic_tone

RATE_HZ = 44100.0
LEVEL_FLOOR_DB = -40.0


@dataclass(frozen=True)
class SeriesCase:
    name: str
    tone: HarmonicTone
    sounding_hz: tuple[float, ...]
    silent_hz: tuple[float, ...]


def _level_db(waveform: NDArray[np.float64], frequency_hz: float) -> float:
    """The waveform's level at one frequency, in decibels under its loudest bin."""
    magnitude = np.abs(np.fft.rfft(waveform[:, 0] * np.hanning(waveform.shape[0])))
    frequencies = np.fft.rfftfreq(waveform.shape[0], d=1.0 / RATE_HZ)
    nearest = int(np.argmin(np.abs(frequencies - frequency_hz)))
    return float(20.0 * np.log10(magnitude[nearest - 2 : nearest + 3].max() / magnitude.max()))


@pytest.mark.parametrize(
    "case",
    [
        SeriesCase(
            name="full series",
            tone=HarmonicTone(fundamental_hz=200.0, resonance_hz=1000.0),
            sounding_hz=(200.0, 400.0, 600.0),
            silent_hz=(300.0, 500.0),
        ),
        SeriesCase(
            name="fundamental left out",
            tone=HarmonicTone(fundamental_hz=200.0, resonance_hz=1000.0, lowest_harmonic=3),
            sounding_hz=(600.0, 800.0, 1000.0),
            silent_hz=(200.0, 400.0),
        ),
        SeriesCase(
            name="stiff string",
            tone=HarmonicTone(fundamental_hz=200.0, resonance_hz=1000.0, inharmonicity=0.01),
            sounding_hz=(200.0 * np.sqrt(1.01), 1000.0 * np.sqrt(1.25)),
            silent_hz=(1000.0,),
        ),
    ],
    ids=lambda case: case.name,
)
def test_a_tone_sounds_its_series_and_nothing_between(case: SeriesCase) -> None:
    waveform = harmonic_tone(case.tone, rate_hz=RATE_HZ)

    assert all(_level_db(waveform, frequency) > LEVEL_FLOOR_DB for frequency in case.sounding_hz)
    assert all(_level_db(waveform, frequency) < LEVEL_FLOOR_DB for frequency in case.silent_hz)


def test_a_tone_lasts_its_seconds_in_one_channel() -> None:
    waveform = harmonic_tone(HarmonicTone(fundamental_hz=110.0, resonance_hz=900.0, seconds=0.25), rate_hz=RATE_HZ)

    assert waveform.shape == (int(0.25 * RATE_HZ), 1)


def test_a_tone_between_two_stands_on_the_geometric_line_between_their_positions() -> None:
    low = HarmonicTone(fundamental_hz=100.0, resonance_hz=1000.0, lowest_harmonic=2)
    high = HarmonicTone(fundamental_hz=400.0, resonance_hz=4000.0, lowest_harmonic=2)

    middle = low.between(high, weight=0.5)

    assert middle == HarmonicTone(
        fundamental_hz=pytest.approx(200.0), resonance_hz=pytest.approx(2000.0), lowest_harmonic=2
    )
