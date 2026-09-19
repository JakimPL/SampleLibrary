from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import SEMITONES_PER_OCTAVE

TONE_SECONDS: Final[float] = 1.0
ATTACK_SECONDS: Final[float] = 0.005
DECAY_SECONDS: Final[float] = 0.5
HARMONIC_TILT_DB_PER_OCTAVE: Final[float] = -6.0
RESONANCE_GAIN_DB: Final[float] = 24.0
RESONANCE_WIDTH_SEMITONES: Final[float] = 3.0
HIGHEST_HARMONIC_SHARE_OF_RATE: Final[float] = 0.45
TONE_PEAK: Final[float] = 0.5


@dataclass(frozen=True)
class ResonantTone:
    """A harmonic tone shaped by one resonance: where its series stands and where its body rings."""

    fundamental_hz: float
    resonance_hz: float

    def between(self, other: ResonantTone, *, weight: float) -> ResonantTone:
        """The tone `weight` of the way to another, both positions on the geometric line between them."""
        return ResonantTone(
            fundamental_hz=float(self.fundamental_hz ** (1.0 - weight) * other.fundamental_hz**weight),
            resonance_hz=float(self.resonance_hz ** (1.0 - weight) * other.resonance_hz**weight),
        )


def resonant_tone(tone: ResonantTone, *, rate_hz: float) -> NDArray[np.float64]:
    """A struck harmonic tone whose partials fall off with the tilt and rise into the resonance.

    Every partial's level is the tilt at its harmonic number plus a Gaussian bump centered on the
    resonance in semitones, so moving the fundamental moves the partials under a body that stays,
    and moving the resonance moves the body over partials that stay. The phases follow Schroeder's
    quadratic rule, which keeps the waveform's peak low whatever the number of partials. Shape:
    ``(frames, 1)``, one channel, the shape a stored waveform has.
    """
    times = np.arange(int(round(TONE_SECONDS * rate_hz)), dtype=np.float64) / rate_hz
    harmonic_count = max(int(HIGHEST_HARMONIC_SHARE_OF_RATE * rate_hz / tone.fundamental_hz), 1)
    harmonics = np.arange(1, harmonic_count + 1, dtype=np.float64)
    frequencies = harmonics * tone.fundamental_hz
    distance_semitones = SEMITONES_PER_OCTAVE * np.log2(frequencies / tone.resonance_hz)
    levels_db = HARMONIC_TILT_DB_PER_OCTAVE * np.log2(harmonics) + RESONANCE_GAIN_DB * np.exp(
        -0.5 * (distance_semitones / RESONANCE_WIDTH_SEMITONES) ** 2
    )
    amplitudes = 10.0 ** (levels_db / 20.0)
    phases = np.pi * harmonics**2 / harmonic_count
    waveform = np.zeros_like(times)
    for frequency, amplitude, phase in zip(frequencies, amplitudes, phases, strict=True):
        waveform += amplitude * np.sin(2.0 * np.pi * frequency * times + phase)
    envelope = np.minimum(times / ATTACK_SECONDS, 1.0) * np.exp(-times / DECAY_SECONDS)
    struck = waveform * envelope
    scaled: NDArray[np.float64] = TONE_PEAK * struck / float(np.abs(struck).max())
    return scaled[:, None]
