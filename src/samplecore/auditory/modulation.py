from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from functools import cache
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.envelope import (
    COMPRESSION_EXPONENT,
    ENVELOPE_FLOOR,
    MODULATION_ENVELOPE_RATE_HZ,
    compress,
    decimate,
    decimation_kernel,
    subband_envelopes,
)
from samplecore.auditory.filterbank import GammatoneBank, design_gammatone_bank
from samplecore.auditory.framing import frame_series, hann_taper

MODULATION_DEPTH_FLOOR: Final[float] = 0.05
MINIMUM_WINDOW_LENGTH: Final[int] = 3


@unique
class ModulationAxis(StrEnum):
    FLUCTUATION = "fluctuation"
    ROUGHNESS = "roughness"


@dataclass(frozen=True)
class ModulationLobe:
    """One psychoacoustic modulation axis: where its sensitivity peaks, where it has faded, and
    how long an envelope window resolves it."""

    axis: ModulationAxis
    peak_hz: float
    lower_edge_hz: float
    upper_edge_hz: float
    window_seconds: float

    def bin_weights(self, *, envelope_rate_hz: float, window_length: int) -> NDArray[np.float64]:
        """How much each modulation bin of a window this long counts toward the lobe, summing to one.

        The weight is a triangle in log-frequency, rising from the lower edge to the peak and
        falling to the upper edge, so sensitivity grows and fades over octaves the way the
        listening data describe it. A window too short to place any bin inside the lobe reads
        every bin alike.
        """
        frequencies = np.fft.rfftfreq(window_length, 1.0 / envelope_rate_hz)
        octaves = np.log2(frequencies, where=frequencies > 0.0, out=np.full_like(frequencies, -np.inf))
        rising = (octaves - np.log2(self.lower_edge_hz)) / (np.log2(self.peak_hz) - np.log2(self.lower_edge_hz))
        falling = (np.log2(self.upper_edge_hz) - octaves) / (np.log2(self.upper_edge_hz) - np.log2(self.peak_hz))
        weights = np.clip(np.minimum(rising, falling), 0.0, 1.0)
        total = float(weights.sum())
        normalized: NDArray[np.float64] = weights / total if total > 0.0 else np.full_like(weights, 1.0 / weights.size)
        return normalized


FLUCTUATION_LOBE: Final[ModulationLobe] = ModulationLobe(
    axis=ModulationAxis.FLUCTUATION, peak_hz=4.0, lower_edge_hz=1.0, upper_edge_hz=20.0, window_seconds=0.4
)
ROUGHNESS_LOBE: Final[ModulationLobe] = ModulationLobe(
    axis=ModulationAxis.ROUGHNESS, peak_hz=70.0, lower_edge_hz=20.0, upper_edge_hz=150.0, window_seconds=0.2
)
MODULATION_LOBES: Final[tuple[ModulationLobe, ...]] = (FLUCTUATION_LOBE, ROUGHNESS_LOBE)


@dataclass(frozen=True)
class ModulationFrontEnd:
    """The one design every applier of the modulation reading follows.

    A gammatone bank, the decimation that follows its envelopes, and the lobes the modulation
    spectrum is read through are decided once here, as data, so a reading in numpy and a loss in
    another array library apply the same kernels and the same framing and agree to rounding. The
    lobes are the two a listener hears a phase gargle on: fluctuation strength peaking at 4 Hz and
    roughness peaking at 70 Hz (Fastl and Zwicker, 2007; Daniel and Weber, 1997), and the envelope
    rate keeps the roughness lobe's upper edge below its Nyquist frequency.
    """

    bank: GammatoneBank
    decimation_factor: int
    decimation_kernel: NDArray[np.float64]
    lobes: tuple[ModulationLobe, ...]

    @property
    def sample_rate_hz(self) -> int:
        return self.bank.sample_rate_hz

    @property
    def envelope_rate_hz(self) -> float:
        return self.bank.sample_rate_hz / self.decimation_factor

    @property
    def compressed_floor(self) -> float:
        return float(ENVELOPE_FLOOR**COMPRESSION_EXPONENT)

    @property
    def depth_floor(self) -> float:
        """The modulation depth a listener first detects, read in the compressed domain.

        A depth of `MODULATION_DEPTH_FLOOR` (Viemeister, 1979) on a linear envelope reads a third as
        deep after the cube root, so the floor follows the compression.
        """
        return COMPRESSION_EXPONENT * MODULATION_DEPTH_FLOOR

    def window_length(self, lobe: ModulationLobe, *, envelope_length: int) -> int:
        """How many envelope points one frame of `lobe` spans, whole-clip for a clip shorter than that."""
        return max(min(round(lobe.window_seconds * self.envelope_rate_hz), envelope_length), MINIMUM_WINDOW_LENGTH)

    def hop_length(self, window_length: int) -> int:
        return max(window_length // 2, 1)


@cache
def design_modulation_front_end(*, sample_rate_hz: int) -> ModulationFrontEnd:
    """Design the front end for one sample rate, with the envelope read at `MODULATION_ENVELOPE_RATE_HZ`."""
    factor = max(round(sample_rate_hz / MODULATION_ENVELOPE_RATE_HZ), 1)
    return ModulationFrontEnd(
        bank=design_gammatone_bank(sample_rate_hz=sample_rate_hz),
        decimation_factor=factor,
        decimation_kernel=decimation_kernel(factor),
        lobes=MODULATION_LOBES,
    )


@dataclass(frozen=True)
class ModulationSpectrum:
    """One lobe's reading of one waveform.

    `depth` is the modulation depth per channel, frame and modulation bin, with everything under the
    detection floor already taken out; `level` is the compressed level each frame was read at; and
    `bin_weight` says how much each bin counts toward the lobe.
    """

    lobe: ModulationLobe
    depth: NDArray[np.float64]  # (channels, frames, bins)
    level: NDArray[np.float64]  # (channels, frames)
    bin_weight: NDArray[np.float64]  # (bins,)


def compressed_envelopes(waveform: NDArray[np.float64], *, front_end: ModulationFrontEnd) -> NDArray[np.float64]:
    """Each channel's compressed envelope at the envelope rate, shaped ``(channels, points)``."""
    return decimate(compress(subband_envelopes(waveform, bank=front_end.bank)), factor=front_end.decimation_factor)


def modulation_spectra(
    waveform: NDArray[np.float64], *, front_end: ModulationFrontEnd
) -> tuple[ModulationSpectrum, ...]:
    """Read the waveform's modulation through every lobe of the front end, one spectrum per lobe.

    Raises:
        ValueError: the waveform spans fewer envelope points than the shortest window it can be read through.
    """
    envelopes = compressed_envelopes(waveform, front_end=front_end)
    if envelopes.shape[-1] < MINIMUM_WINDOW_LENGTH:
        raise ValueError(
            f"a waveform of {waveform.shape[0]} samples spans {envelopes.shape[-1]} envelope points, "
            f"and a modulation reading needs at least {MINIMUM_WINDOW_LENGTH}"
        )

    return tuple(_lobe_spectrum(envelopes, lobe=lobe, front_end=front_end) for lobe in front_end.lobes)


def _lobe_spectrum(
    envelopes: NDArray[np.float64], *, lobe: ModulationLobe, front_end: ModulationFrontEnd
) -> ModulationSpectrum:
    """One lobe's depth spectrum, read so a sinusoidal modulation of depth `m` reads `m`.

    Each frame's mean leaves before the taper is applied, so a steady envelope reads no
    modulation at all: the taper's own spectral spread would otherwise carry the frame's level
    into the lowest bins and read as slow fluctuation.
    """
    window_length = front_end.window_length(lobe, envelope_length=envelopes.shape[-1])
    frames = frame_series(envelopes, window_length=window_length, hop_length=front_end.hop_length(window_length))
    level = frames.mean(axis=-1)
    taper = hann_taper(window_length)
    spectrum = np.abs(np.fft.rfft((frames - level[..., None]) * taper, axis=-1))
    depth = 2.0 * spectrum / np.maximum(level, front_end.compressed_floor)[..., None] / taper.sum()
    return ModulationSpectrum(
        lobe=lobe,
        depth=np.maximum(depth - front_end.depth_floor, 0.0),
        level=level,
        bin_weight=lobe.bin_weights(envelope_rate_hz=front_end.envelope_rate_hz, window_length=window_length),
    )
