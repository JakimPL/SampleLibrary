from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import SEMITONES_PER_OCTAVE

DEFAULT_TONE_SECONDS: Final[float] = 1.0
FULL_SERIES: Final[int] = 1
HARMONIC_SERIES: Final[float] = 0.0
DEFAULT_TILT_DB_PER_OCTAVE: Final[float] = -6.0
DEFAULT_RESONANCE_GAIN_DB: Final[float] = 24.0
RESONANCE_WIDTH_SEMITONES: Final[float] = 3.0
ATTACK_SECONDS: Final[float] = 0.005
DECAY_SECONDS: Final[float] = 0.5
HIGHEST_PARTIAL_SHARE_OF_RATE: Final[float] = 0.45
TONE_PEAK: Final[float] = 0.5


@dataclass(frozen=True)
class HarmonicTone:
    """A struck tone with a known pitch: where its series stands, how its partials fall, and where its body rings.

    The series starts at `lowest_harmonic`, so a tone whose fundamental is left out still sounds
    its pitch through the harmonics above it. `inharmonicity` stretches the series the way a stiff
    string does, with partial `n` at `n · f0 · sqrt(1 + B·n²)`. The partials fall with the tilt and
    rise by `resonance_gain_db` into a resonance three semitones wide, which is how a body shapes
    the series it carries.
    """

    fundamental_hz: float
    resonance_hz: float
    lowest_harmonic: int = FULL_SERIES
    inharmonicity: float = HARMONIC_SERIES
    tilt_db_per_octave: float = DEFAULT_TILT_DB_PER_OCTAVE
    resonance_gain_db: float = DEFAULT_RESONANCE_GAIN_DB
    seconds: float = DEFAULT_TONE_SECONDS

    def between(self, other: HarmonicTone, *, weight: float) -> HarmonicTone:
        """The tone `weight` of the way to another, its series and its body on the geometric line between them."""
        return replace(
            self,
            fundamental_hz=float(self.fundamental_hz ** (1.0 - weight) * other.fundamental_hz**weight),
            resonance_hz=float(self.resonance_hz ** (1.0 - weight) * other.resonance_hz**weight),
        )


def harmonic_tone(tone: HarmonicTone, *, rate_hz: float) -> NDArray[np.float64]:
    """A struck tone whose partials fall off with the tilt and rise into the resonance.

    The series reaches up to `HIGHEST_PARTIAL_SHARE_OF_RATE` of the rate, clear of aliasing. The
    phases follow Schroeder's quadratic rule, which keeps the waveform's peak low whatever the number
    of partials, and the tone is scaled to `TONE_PEAK`. Shape: ``(frames, 1)``, one channel, the
    shape a stored waveform has.
    """
    times = np.arange(int(round(tone.seconds * rate_hz)), dtype=np.float64) / rate_hz
    harmonics, frequencies = _series(tone, rate_hz=rate_hz)
    distance_semitones = SEMITONES_PER_OCTAVE * np.log2(frequencies / tone.resonance_hz)
    levels_db = tone.tilt_db_per_octave * np.log2(harmonics) + tone.resonance_gain_db * np.exp(
        -0.5 * (distance_semitones / RESONANCE_WIDTH_SEMITONES) ** 2
    )
    amplitudes = 10.0 ** (levels_db / 20.0)
    phases = np.pi * harmonics**2 / harmonics[-1]
    waveform = np.zeros_like(times)
    for frequency, amplitude, phase in zip(frequencies, amplitudes, phases, strict=True):
        waveform += amplitude * np.sin(2.0 * np.pi * frequency * times + phase)
    envelope = np.minimum(times / ATTACK_SECONDS, 1.0) * np.exp(-times / DECAY_SECONDS)
    struck = waveform * envelope
    scaled: NDArray[np.float64] = TONE_PEAK * struck / float(np.abs(struck).max())
    return scaled[:, None]


def _series(tone: HarmonicTone, *, rate_hz: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The harmonic numbers a tone sounds at this rate, and their frequencies, the lowest harmonic always among them."""
    highest_hz = HIGHEST_PARTIAL_SHARE_OF_RATE * rate_hz
    count = max(int(highest_hz / tone.fundamental_hz), tone.lowest_harmonic)
    harmonics = np.arange(tone.lowest_harmonic, count + 1, dtype=np.float64)
    frequencies = harmonics * tone.fundamental_hz * np.sqrt(1.0 + tone.inharmonicity * harmonics**2)
    kept = (frequencies <= highest_hz) | (harmonics == tone.lowest_harmonic)
    return harmonics[kept], frequencies[kept]
