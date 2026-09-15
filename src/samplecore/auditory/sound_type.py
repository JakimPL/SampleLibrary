from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.envelope import local_rms_envelope
from samplecore.auditory.framing import frame_series, hann_taper

ANALYSIS_FFT_LENGTH: Final[int] = 2048
ANALYSIS_HOP_LENGTH: Final[int] = 512
FLATNESS_LOWEST_HZ: Final[float] = 50.0
FLATNESS_HIGHEST_HZ: Final[float] = 16000.0
NOISE_FLATNESS_THRESHOLD: Final[float] = 0.2
SUSTAIN_DEPTH_DB: Final[float] = 12.0
ONSET_LOOKBACK_SECONDS: Final[float] = 0.02
PERCUSSIVE_DECAY_SECONDS: Final[float] = 0.5
PERCUSSIVE_ATTACK_SECONDS: Final[float] = 0.1
PERCUSSIVE_THRESHOLD: Final[float] = 0.5
HARMONICITY_LOWEST_HZ: Final[float] = 50.0
HARMONICITY_HIGHEST_HZ: Final[float] = 2000.0
HARMONICITY_FRAME_LENGTH: Final[int] = 4096
HARMONICITY_HOP_LENGTH: Final[int] = 2048
TONAL_HARMONICITY_THRESHOLD: Final[float] = 0.6
POWER_FLOOR: Final[float] = 1e-20


@unique
class SoundType(StrEnum):
    TONAL = "tonal"
    PERCUSSIVE = "percussive"
    NOISE = "noise"


@dataclass(frozen=True)
class SoundTypeReading:
    """Three acoustic readings of a sample, each in ``[0, 1]``, and the type they resolve to.

    `flatness` is the Wiener entropy of the power spectrum: white noise reads near 0.56 frame by
    frame and a line spectrum well under 0.05. `percussiveness` is how fast the clip's strikes
    arrive and fall away, each strike read on its own, so a struck sound and a loop of struck sounds
    read high and a held one reads near zero. `harmonicity` is the normalized autocorrelation peak
    over the pitch range (Boersma, 1993), one for a perfectly periodic sound. The readings stay
    beside the verdict so a stratified table can say why a probe landed where it did.
    """

    flatness: float
    percussiveness: float
    harmonicity: float

    @property
    def sound_type(self) -> SoundType:
        """A struck sound is percussive whatever its spectrum; a held one is noise when it is flat and
        aperiodic, and tonal otherwise -- a pulse train is flat yet periodic, hence the conjunction,
        and a sustained inharmonic bell is tonal, the bucket a phase gargle applies to."""
        if self.percussiveness >= PERCUSSIVE_THRESHOLD:
            return SoundType.PERCUSSIVE
        if self.flatness >= NOISE_FLATNESS_THRESHOLD and self.harmonicity < TONAL_HARMONICITY_THRESHOLD:
            return SoundType.NOISE
        return SoundType.TONAL


def sound_type_reading(mono: NDArray[np.float64], *, sample_rate_hz: int) -> SoundTypeReading:
    """Read what kind of sound a mono waveform is, at the rate its frames are heard at.

    Raises:
        ValueError: the waveform is silent, so it has nothing to classify.
    """
    if float(np.abs(mono).max()) == 0.0:
        raise ValueError("a silent waveform has nothing to classify")

    return SoundTypeReading(
        flatness=_spectral_flatness(mono, sample_rate_hz=sample_rate_hz),
        percussiveness=_percussiveness(mono, sample_rate_hz=sample_rate_hz),
        harmonicity=_harmonicity(mono, sample_rate_hz=sample_rate_hz),
    )


def _energy_weighted(readings: NDArray[np.float64], energies: NDArray[np.float64]) -> float:
    """A mean over frames counting each by its energy, so silence between sounds says nothing."""
    total = float(energies.sum())
    return float((readings * energies).sum() / total) if total > 0.0 else float(readings.mean())


def _spectral_flatness(mono: NDArray[np.float64], *, sample_rate_hz: int) -> float:
    """The geometric over the arithmetic mean of each frame's power inside the audible band, energy-weighted.

    The analysis window shrinks to fit a clip shorter than it, so a brief sound still reads as one
    frame of its own spectrum.
    """
    length = min(ANALYSIS_FFT_LENGTH, mono.shape[0])
    frames = frame_series(mono, window_length=length, hop_length=min(ANALYSIS_HOP_LENGTH, length))
    power = np.abs(np.fft.rfft(frames * hann_taper(length), axis=-1)) ** 2
    frequencies = np.fft.rfftfreq(length, 1.0 / sample_rate_hz)
    within_band = (frequencies >= FLATNESS_LOWEST_HZ) & (frequencies <= FLATNESS_HIGHEST_HZ)
    banded = power[:, within_band] + POWER_FLOOR
    flatness = np.exp(np.log(banded).mean(axis=1)) / banded.mean(axis=1)
    return _energy_weighted(flatness, banded.sum(axis=1))


def _percussiveness(mono: NDArray[np.float64], *, sample_rate_hz: int) -> float:
    """How fast the clip's strikes arrive and fall away, each strike scored on its own and weighted by its energy.

    The clip is cut into strikes wherever the level climbs `SUSTAIN_DEPTH_DB` within
    `ONSET_LOOKBACK_SECONDS`, so a loop of hits is read hit by hit. A strike scores by the time
    its level takes to fall `SUSTAIN_DEPTH_DB` below its peak, full marks at once and none at
    `PERCUSSIVE_DECAY_SECONDS`, scaled by how promptly the peak arrived, none at
    `PERCUSSIVE_ATTACK_SECONDS`. Absolute times keep a kick a kick whatever the clip's length, and
    a struck sound that rings on -- a cymbal, a plucked string -- reads low, since its identity is
    carried by what sustains. Checked against sample names that state a role, nine in ten leads,
    pads and vocals read under the percussive bar, and the struck roles split along exactly that ring.
    """
    level = local_rms_envelope(mono, sample_rate_hz=sample_rate_hz)
    decibels = 20.0 * np.log10(level / float(level.max()))
    lookback = max(int(ONSET_LOOKBACK_SECONDS * sample_rate_hz), 1)
    rise = decibels[lookback:] - decibels[:-lookback]
    climbing = np.concatenate((np.zeros(lookback, dtype=bool), rise >= SUSTAIN_DEPTH_DB))
    onsets = np.flatnonzero(climbing[1:] & ~climbing[:-1]) + 1
    starts = np.concatenate(([0], onsets))
    ends = np.concatenate((onsets, [decibels.shape[0]]))
    scores = np.array(
        [_strike_score(decibels[start:end], sample_rate_hz=sample_rate_hz) for start, end in zip(starts, ends)]
    )
    energies = np.array([float((level[start:end] ** 2).sum()) for start, end in zip(starts, ends)])
    return _energy_weighted(scores, energies)


def _strike_score(decibels: NDArray[np.float64], *, sample_rate_hz: int) -> float:
    """One strike's percussiveness from its level in decibels relative to the clip's peak."""
    peak_index = int(np.argmax(decibels))
    fallen = np.flatnonzero(decibels[peak_index:] < decibels[peak_index] - SUSTAIN_DEPTH_DB)
    decay_seconds = (int(fallen[0]) if fallen.size > 0 else decibels.shape[0] - peak_index) / sample_rate_hz
    decay_credit = float(np.clip(1.0 - decay_seconds / PERCUSSIVE_DECAY_SECONDS, 0.0, 1.0))
    attack_credit = float(np.clip(1.0 - peak_index / sample_rate_hz / PERCUSSIVE_ATTACK_SECONDS, 0.0, 1.0))
    return decay_credit * attack_credit


def _harmonicity(mono: NDArray[np.float64], *, sample_rate_hz: int) -> float:
    """The normalized autocorrelation peak over the pitch range, energy-weighted across frames.

    Each frame's autocorrelation is divided by the window's own, which is what lets a lag near the
    frame's end read at its true strength (Boersma, 1993). Lags are held to half the frame, where
    that correction stays well conditioned.
    """
    length = min(HARMONICITY_FRAME_LENGTH, mono.shape[0])
    taper = hann_taper(length)
    frames = frame_series(mono, window_length=length, hop_length=min(HARMONICITY_HOP_LENGTH, length)) * taper
    fft_size = 2 * length
    frame_correlation = np.fft.irfft(np.abs(np.fft.rfft(frames, n=fft_size, axis=-1)) ** 2, axis=-1)[:, :length]
    taper_correlation = np.fft.irfft(np.abs(np.fft.rfft(taper, n=fft_size)) ** 2)[:length]
    lowest_lag = max(int(sample_rate_hz / HARMONICITY_HIGHEST_HZ), 1)
    highest_lag = min(int(sample_rate_hz / HARMONICITY_LOWEST_HZ), length // 2)
    energies = frame_correlation[:, 0]
    normalized = frame_correlation[:, lowest_lag : highest_lag + 1] / np.maximum(energies[:, None], POWER_FLOOR)
    normalized /= taper_correlation[None, lowest_lag : highest_lag + 1] / taper_correlation[0]
    peaks = np.clip(normalized.max(axis=1), 0.0, 1.0) if normalized.shape[1] > 0 else np.zeros(frames.shape[0])
    return _energy_weighted(peaks, energies)
