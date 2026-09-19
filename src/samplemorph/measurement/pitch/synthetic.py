from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray
from trackmod.core.samples.depth import BitDepth

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.waveform import requantized
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.geometry import SEMITONES_PER_OCTAVE, semitones_from_reference
from samplemorph.tones import (
    DEFAULT_TONE_SECONDS,
    FULL_SERIES,
    HARMONIC_SERIES,
    TONE_PEAK,
    HarmonicTone,
    harmonic_tone,
    struck_envelope,
)

# The rate a tracker plays a sample's untransposed middle C at, which most 8-bit samples were made for.
TRACKER_RATE_HZ: Final[int] = 8363
LOWEST_FUNDAMENTAL_HZ: Final[float] = 40.0
HIGHEST_FUNDAMENTAL_HZ: Final[float] = 640.0
PLAIN_TILT_DB_PER_OCTAVE: Final[float] = -6.0
STEEP_TILT_DB_PER_OCTAVE: Final[float] = -15.0
FLAT_TILT_DB_PER_OCTAVE: Final[float] = 0.0
RESONANCE_GAIN_DB: Final[float] = 24.0
NO_RESONANCE_DB: Final[float] = 0.0
RESONANT_HARMONICS: Final[tuple[int, ...]] = (1, 2, 3, 4, 5, 6)
MISSING_FUNDAMENTAL_LOWEST_HARMONIC: Final[int] = 2
# A piano's wound bass strings stretch their partials by about this much.
STIFF_STRING_INHARMONICITY: Final[float] = 4e-4
PAIR_INTERVALS_SEMITONES: Final[tuple[float, ...]] = (1.0, 3.0, 5.0, 7.0, 12.0, 17.0)
# White, pink and brown: the power falling by none, one and two powers of the frequency.
NOISE_EXPONENTS: Final[tuple[float, ...]] = (0.0, 1.0, 2.0)


@unique
class Rendering(StrEnum):
    """How a synthetic sound is stored before it is read.

    `CLEAN` renders at the nominal rate. `EIGHT_BIT` renders at `TRACKER_RATE_HZ` and stores the
    result at 8 bits, as a tracker's sample is made; read in the nominal frame it sounds higher by
    the interval between the two rates, with its harmonics reaching the top of the frame.
    """

    CLEAN = "clean"
    EIGHT_BIT = "eight-bit"

    @property
    def rate_hz(self) -> float:
        match self:
            case Rendering.CLEAN:
                return float(NOMINAL_WAV_RATE)
            case Rendering.EIGHT_BIT:
                return float(TRACKER_RATE_HZ)

    @property
    def nominal_offset_semitones(self) -> float:
        """How far a sound rendered this way moves once it is read at the nominal rate."""
        return SEMITONES_PER_OCTAVE * float(np.log2(NOMINAL_WAV_RATE / self.rate_hz))

    def stored(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        match self:
            case Rendering.CLEAN:
                return waveform
            case Rendering.EIGHT_BIT:
                return requantized(waveform, depth=BitDepth.EIGHT)


@dataclass(frozen=True)
class ToneFamily:
    """A timbre synthetic tones are drawn in: where the series starts, how stiff it is, how it falls and where its body rings.

    The resonance sits on harmonic `resonance_harmonic` of every tone drawn, so it follows the
    series wherever its fundamental lies.
    """

    name: str
    lowest_harmonic: int
    inharmonicity: float
    tilt_db_per_octave: float
    resonance_harmonic: int
    resonance_gain_db: float

    def tone(self, fundamental_hz: float) -> HarmonicTone:
        return HarmonicTone(
            fundamental_hz=fundamental_hz,
            resonance_hz=self.resonance_harmonic * fundamental_hz,
            lowest_harmonic=self.lowest_harmonic,
            inharmonicity=self.inharmonicity,
            tilt_db_per_octave=self.tilt_db_per_octave,
            resonance_gain_db=self.resonance_gain_db,
        )


def _plain(name: str, *, tilt_db_per_octave: float) -> ToneFamily:
    return ToneFamily(
        name=name,
        lowest_harmonic=FULL_SERIES,
        inharmonicity=HARMONIC_SERIES,
        tilt_db_per_octave=tilt_db_per_octave,
        resonance_harmonic=FULL_SERIES,
        resonance_gain_db=NO_RESONANCE_DB,
    )


PLAIN_FAMILY: Final[ToneFamily] = _plain("plain", tilt_db_per_octave=PLAIN_TILT_DB_PER_OCTAVE)
TONE_FAMILIES: Final[tuple[ToneFamily, ...]] = (
    PLAIN_FAMILY,
    *(
        ToneFamily(
            name=f"resonance-on-{harmonic}",
            lowest_harmonic=FULL_SERIES,
            inharmonicity=HARMONIC_SERIES,
            tilt_db_per_octave=PLAIN_TILT_DB_PER_OCTAVE,
            resonance_harmonic=harmonic,
            resonance_gain_db=RESONANCE_GAIN_DB,
        )
        for harmonic in RESONANT_HARMONICS
    ),
    _plain("steep", tilt_db_per_octave=STEEP_TILT_DB_PER_OCTAVE),
    _plain("flat", tilt_db_per_octave=FLAT_TILT_DB_PER_OCTAVE),
    ToneFamily(
        name="missing-fundamental",
        lowest_harmonic=MISSING_FUNDAMENTAL_LOWEST_HARMONIC,
        inharmonicity=HARMONIC_SERIES,
        tilt_db_per_octave=PLAIN_TILT_DB_PER_OCTAVE,
        resonance_harmonic=FULL_SERIES,
        resonance_gain_db=NO_RESONANCE_DB,
    ),
    ToneFamily(
        name="stiff",
        lowest_harmonic=FULL_SERIES,
        inharmonicity=STIFF_STRING_INHARMONICITY,
        tilt_db_per_octave=PLAIN_TILT_DB_PER_OCTAVE,
        resonance_harmonic=FULL_SERIES,
        resonance_gain_db=NO_RESONANCE_DB,
    ),
)


@dataclass(frozen=True)
class RenderedTone:
    """One synthetic tone of a family, stored the way `rendering` says, under a name its readings carry."""

    name: str
    family: ToneFamily
    tone: HarmonicTone
    rendering: Rendering

    @property
    def group(self) -> str:
        """What its readings are gathered under: the family, and the rendering when it is not the clean one."""
        match self.rendering:
            case Rendering.CLEAN:
                return self.family.name
            case Rendering.EIGHT_BIT:
                return f"{self.family.name}-{self.rendering.value}"

    @property
    def truth_semitones(self) -> float:
        """The pitch the tone sounds at once read in the nominal frame."""
        return semitones_from_reference(self.tone.fundamental_hz) + self.rendering.nominal_offset_semitones

    def render(self) -> PreparedMono:
        return prepare_mono(self.rendering.stored(harmonic_tone(self.tone, rate_hz=self.rendering.rate_hz)))


@dataclass(frozen=True)
class TonePair:
    """Two clean tones of different families, the second `interval_semitones` above the first."""

    name: str
    first: RenderedTone
    second: RenderedTone
    interval_semitones: float


@dataclass(frozen=True)
class NoiseBurst:
    """A struck burst of noise whose power falls as the frequency raised to `exponent`, a sound with no pitch to read."""

    name: str
    exponent: float
    random_seed: int

    def render(self) -> PreparedMono:
        frame_count = int(round(DEFAULT_TONE_SECONDS * NOMINAL_WAV_RATE))
        spectrum = np.fft.rfft(np.random.default_rng(self.random_seed).standard_normal(frame_count))
        frequencies = np.fft.rfftfreq(frame_count, d=1.0 / NOMINAL_WAV_RATE)
        spectrum[0] = 0.0
        spectrum[1:] *= frequencies[1:] ** (-self.exponent / 2.0)
        times = np.arange(frame_count, dtype=np.float64) / NOMINAL_WAV_RATE
        struck = np.fft.irfft(spectrum, n=frame_count) * struck_envelope(times)
        return prepare_mono((TONE_PEAK * struck / float(np.abs(struck).max()))[:, None])


def draw_family_tones(*, count: int, random_seed: int) -> tuple[RenderedTone, ...]:
    """`count` tones of every family at fundamentals drawn evenly in octaves over the synthetic register, each stored both ways.

    One draw of fundamentals serves every family, so the families differ in timbre alone.
    """
    fundamentals = _fundamentals(np.random.default_rng(random_seed), count=count)
    return tuple(
        RenderedTone(
            name=f"{family.name}-{index:02d}-{rendering.value}",
            family=family,
            tone=family.tone(float(fundamental_hz)),
            rendering=rendering,
        )
        for family in TONE_FAMILIES
        for rendering in Rendering
        for index, fundamental_hz in enumerate(fundamentals)
    )


def draw_tone_pairs(*, count: int, random_seed: int) -> tuple[TonePair, ...]:
    """`count` pairs of clean tones in two different families, a drawn interval apart either way, both within the register."""
    generator = np.random.default_rng(random_seed)
    pairs = []
    for index in range(count):
        first_family, second_family = generator.choice(len(TONE_FAMILIES), size=2, replace=False)
        interval = float(generator.choice(PAIR_INTERVALS_SEMITONES)) * float(generator.choice((-1.0, 1.0)))
        ratio = 2.0 ** (interval / SEMITONES_PER_OCTAVE)
        lowest, highest = LOWEST_FUNDAMENTAL_HZ * max(1.0, 1.0 / ratio), HIGHEST_FUNDAMENTAL_HZ * min(1.0, 1.0 / ratio)
        fundamental_hz = float(np.exp(generator.uniform(np.log(lowest), np.log(highest))))
        pairs.append(
            TonePair(
                name=f"pair-{index:02d}",
                first=_clean_tone(f"pair-{index:02d}-first", TONE_FAMILIES[first_family], fundamental_hz),
                second=_clean_tone(f"pair-{index:02d}-second", TONE_FAMILIES[second_family], fundamental_hz * ratio),
                interval_semitones=interval,
            )
        )
    return tuple(pairs)


def draw_noise_bursts(*, count: int, random_seed: int) -> tuple[NoiseBurst, ...]:
    """`count` noise bursts, the colors taken in turn, each on its own seed."""
    return tuple(
        NoiseBurst(
            name=f"noise-{index:02d}",
            exponent=NOISE_EXPONENTS[index % len(NOISE_EXPONENTS)],
            random_seed=random_seed + index,
        )
        for index in range(count)
    )


def _clean_tone(name: str, family: ToneFamily, fundamental_hz: float) -> RenderedTone:
    return RenderedTone(name=name, family=family, tone=family.tone(fundamental_hz), rendering=Rendering.CLEAN)


def _fundamentals(generator: np.random.Generator, *, count: int) -> NDArray[np.float64]:
    fundamentals: NDArray[np.float64] = np.exp(
        generator.uniform(np.log(LOWEST_FUNDAMENTAL_HZ), np.log(HIGHEST_FUNDAMENTAL_HZ), size=count)
    )
    return fundamentals
