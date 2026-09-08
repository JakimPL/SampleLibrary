from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from samplecloud.backends.preprocessing import fold_to_mono, remove_dc_offset
from samplecore.storage.audio_store import NOMINAL_WAV_RATE

# Envelope/dynamics descriptor -- OptiSample's own level extraction
# (github.com/JakimPL/OptiSample, src/optisample/dsp/envelope.py), reproduced faithfully. `level`
# is read under a Hann-weighted window sized to two periods of ROOT_HZ, a plausible low pitch
# rather than a detected one -- percussion has no fundamental to detect, so every sample is read
# under the same window regardless of content.
PERIODS_PER_KERNEL: Final[int] = 2
ROOT_HZ: Final[float] = 60.0
FLOOR_DB: Final[float] = 72.0
QUIET_LEVEL: Final[float] = 1e-12
ENVELOPE_POINTS: Final[int] = 32

# Spectral/timbral descriptor -- a fixed-size, duration-fraction-normalized Constant-Q Harmonic
# Coefficient (CQHC) spectral component (zafarrafii/CQHC-Python), shift-invariant to a rate/pitch
# reinterpretation by the Fourier shift theorem, with no pitch-detection step.
MINIMUM_FREQUENCY_HZ: Final[float] = 32.70
OCTAVE_RESOLUTION: Final[int] = 12
NUMBER_COEFFICIENTS: Final[int] = 20
SPECTRAL_TIME_POINTS: Final[int] = 8
MINIMUM_STEP_LENGTH: Final[int] = 64
STEP_LENGTH_SECONDS: Final[float] = 0.02


class InvariantFeatureExtractor:
    """Extracts a descriptor invariant to gain and to a sample's rate/pitch interpretation.

    A tracker sample-hash carries no single "true" playback rate -- the same stored waveform is
    routinely retuned across instrument slots -- so a feature computed under one arbitrary rate
    treats every other note the content is used at as unrelated. This descriptor instead separates
    two properties that stay meaningful regardless of rate: the loudness envelope's *shape* over
    normalized duration (``_envelope_shape_descriptor``), and a pitch-independent spectral shape
    (``_spectral_shape_descriptor``), each resampled to a fixed number of points across
    duration-fraction rather than aggregated over however many raw analysis frames a clip's assumed
    rate happens to produce -- the fix that makes both descriptors uniformly stable for percussive,
    tonal, and noise-like content alike, not only pitched material. Gain is normalized away
    separately in each descriptor (peak-normalized envelope; energy-normalized spectral magnitude
    before deconvolution). The two are concatenated after each is independently unit-normalized, so
    neither dominates the other by raw scale.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        mono = remove_dc_offset(fold_to_mono(waveform))
        envelope = _envelope_shape_descriptor(mono, assumed_rate=NOMINAL_WAV_RATE)
        spectral = _spectral_shape_descriptor(mono, assumed_rate=NOMINAL_WAV_RATE)
        return np.concatenate([_unit_normalized(envelope), _unit_normalized(spectral)])


def _unit_normalized(vector: NDArray[np.float64]) -> NDArray[np.float64]:
    return vector / (np.linalg.norm(vector) + 1e-12)


def _resample_to_duration_fraction(values: NDArray[np.float64], point_count: int) -> NDArray[np.float64]:
    """Resample a 1D series, indexed by analysis frame, onto ``point_count`` fixed points spanning
    the clip's own duration-fraction ``[0, 1]``.

    Decouples a descriptor's output length from however many raw analysis frames a clip happens to
    produce -- which varies with the assumed sample rate, and is a noisy, unstable count for a short
    clip -- so the same content interpreted at two different rates lands on directly comparable
    vectors.
    """
    original_fractions = np.linspace(0.0, 1.0, values.shape[0])
    target_fractions = np.linspace(0.0, 1.0, point_count)
    return np.interp(target_fractions, original_fractions, values)


def _hann_kernel(span: int) -> NDArray[np.float64]:
    taps = np.hanning(span + span % 2 + 1)
    return taps / np.sum(taps)


def _weighted_mean(values: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    # fftconvolve's own return type is not precise enough for mypy to carry through division below.
    covered = fftconvolve(np.ones_like(values), kernel, mode="same")
    weighted: NDArray[np.float64] = fftconvolve(values, kernel, mode="same") / covered
    return weighted


def _envelope_shape_descriptor(mono: NDArray[np.float64], *, assumed_rate: int) -> NDArray[np.float64]:
    """A sample's loudness-envelope shape, over normalized duration, peak-normalized to be
    gain-invariant.

    ``level`` is a smooth, strictly positive local RMS envelope -- OptiSample's own technique for
    separating a recording's loudness contour from its spectral content. ``floor`` keeps ``level``
    well away from zero for a near-silent signal, so dividing by it elsewhere never blows up; here
    it only shapes the square root's argument, keeping ``level`` itself finite and smooth throughout.
    """
    kernel = _hann_kernel(round(PERIODS_PER_KERNEL * assumed_rate / ROOT_HZ))
    floor = max(10 ** (-FLOOR_DB / 20) * np.max(np.abs(mono)), QUIET_LEVEL)
    level = np.sqrt(np.maximum(_weighted_mean(mono**2, kernel), 0.0) + floor**2)
    resampled = _resample_to_duration_fraction(level, ENVELOPE_POINTS)
    return resampled / (np.max(resampled) + 1e-12)


def _cqt_bin_count(assumed_rate: int) -> int:
    maximum_frequency = assumed_rate / 2
    return int(round(OCTAVE_RESOLUTION * np.log2(maximum_frequency / MINIMUM_FREQUENCY_HZ)))


def _cqt_hop_length(assumed_rate: int) -> int:
    return max(MINIMUM_STEP_LENGTH, int(2 ** np.ceil(np.log2(STEP_LENGTH_SECONDS * assumed_rate))))


def _energy_normalized_cqt_magnitude(
    mono: NDArray[np.float64], *, assumed_rate: int, bin_count: int, hop_length: int
) -> NDArray[np.float64]:
    """Each CQT frame's magnitude, independently L2-normalized across frequency bins.

    Without this, a deconvolved spectral component's low-order coefficients are dominated by an
    incidental "how many CQT bins does this frame have" energy scale -- itself a function of the
    assumed rate's Nyquist frequency, not genuine spectral shape (diagnosed directly against a real
    pitch-sweep sample whose coefficient 0 alone accounted for most of an otherwise-passing
    descriptor's invariance failure). Normalizing per frame removes that scale before it ever
    reaches the deconvolution below.
    """
    magnitude = np.abs(
        librosa.cqt(
            mono,
            sr=assumed_rate,
            hop_length=hop_length,
            fmin=MINIMUM_FREQUENCY_HZ,
            bins_per_octave=OCTAVE_RESOLUTION,
            n_bins=bin_count,
        )
    )
    frame_norms = np.linalg.norm(magnitude, axis=0, keepdims=True)
    return magnitude / (frame_norms + 1e-12)


def _cqhc_spectral_component(magnitude: NDArray[np.float64], *, bin_count: int) -> NDArray[np.float64]:
    """Per-frame deconvolution of CQT magnitude into a pitch-independent spectral shape.

    CQHC's own ``cqtdeconv`` (zafarrafii/CQHC-Python): a rate or pitch change is a multiplicative
    scaling in linear frequency, which becomes an additive shift along the CQT's log-frequency axis
    -- so the magnitude of this shifted axis's own Fourier transform is exactly shift-invariant by
    the Fourier shift theorem, for any signal, harmonic or not, with no explicit pitch detection.
    """
    transformed = np.fft.fft(magnitude, 2 * bin_count - 1, axis=0)
    return np.real(np.fft.ifft(np.abs(transformed), axis=0))[:bin_count, :]


def _spectral_shape_descriptor(mono: NDArray[np.float64], *, assumed_rate: int) -> NDArray[np.float64]:
    """A sample's pitch-independent spectral shape, over normalized duration.

    Keeps a fixed low-order slice of the deconvolved frequency axis (``NUMBER_COEFFICIENTS``,
    matching CQHC's own default) and resamples the time axis to ``SPECTRAL_TIME_POINTS`` fixed
    points across duration-fraction, rather than aggregating over the raw, rate-dependent CQT frame
    count -- the same fixed-size trick the envelope descriptor uses, and for the same reason: a
    short clip's own frame count is too small and too rate-sensitive a statistic to aggregate over
    directly.
    """
    bin_count = _cqt_bin_count(assumed_rate)
    hop_length = _cqt_hop_length(assumed_rate)
    magnitude = _energy_normalized_cqt_magnitude(
        mono, assumed_rate=assumed_rate, bin_count=bin_count, hop_length=hop_length
    )
    spectral_component = _cqhc_spectral_component(magnitude, bin_count=bin_count)

    coefficient_count = min(NUMBER_COEFFICIENTS, spectral_component.shape[0])
    truncated = spectral_component[:coefficient_count, :]
    resampled = np.stack(
        [
            _resample_to_duration_fraction(truncated[coefficient_index, :], SPECTRAL_TIME_POINTS)
            for coefficient_index in range(coefficient_count)
        ]
    )
    return resampled.flatten()
