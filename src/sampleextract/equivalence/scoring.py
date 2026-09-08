from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import sqrt
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly
from trackmod.core.samples.depth import BitDepth

GAIN_VARIANT_RMS_ERROR_CEILING: Final[float] = 0.02
GAIN_VARIANT_MINIMUM_CONFIDENCE: Final[float] = 0.5
MINIMUM_GAIN: Final[float] = 0.1
MAXIMUM_GAIN: Final[float] = 10.0
GAIN_UNITY_TOLERANCE: Final[float] = 0.05

# One 8-bit quantization step: the smallest amplitude even the library's lowest stored fidelity can
# represent, so content at or below it is indistinguishable from silence regardless of a sample's
# own depth.
TRAILING_SILENCE_THRESHOLD: Final[float] = 1.0 / BitDepth.EIGHT.scale

# How far two independently trailing-trimmed waveforms' lengths may still disagree and be treated as
# the same content -- tight, since candidate generation's own MAX_TRAILING_TRIM_FRAMES already
# absorbed the real silent-tail difference; this only absorbs noise in exactly where each waveform's
# own trim boundary landed.
MAX_TRIM_MISMATCH_FRAMES: Final[int] = 32

MAX_RESAMPLE_DENOMINATOR: Final[int] = 200
MAX_TRIM_LAG_FRAMES: Final[int] = 64
MAX_COMPARISON_FRAMES: Final[int] = 20_000
RESAMPLED_MINIMUM_CONFIDENCE: Final[float] = 0.9


@dataclass(frozen=True)
class RelationScore:
    """A detector's verdict on one candidate pair: how confident, and the evidence backing it."""

    confidence: float
    evidence: dict[str, float]


def _quantization_rms_noise(depth: BitDepth) -> float:
    """The theoretical root-mean-square noise a uniform quantizer at ``depth`` adds to full-scale content."""
    return 1.0 / (depth.scale * sqrt(12.0))


def _gain_variant_ceiling(depth: BitDepth) -> float:
    """The residual-error ceiling for a gain-compensated match at ``depth``.

    Scales ``GAIN_VARIANT_RMS_ERROR_CEILING`` -- set for the 8-bit case, at roughly eight times that
    depth's own theoretical quantization noise -- by the ratio between ``depth``'s theoretical noise
    and 8-bit's, so the same headroom applies regardless of which depth a candidate pair shares.
    """
    return GAIN_VARIANT_RMS_ERROR_CEILING * _quantization_rms_noise(depth) / _quantization_rms_noise(BitDepth.EIGHT)


def score_gain_variant(
    waveform_a: NDArray[np.float64], waveform_b: NDArray[np.float64], *, depth_a: BitDepth, depth_b: BitDepth
) -> RelationScore | None:
    """How closely two waveforms match once trailing-length disagreement and the best-fitting global
    gain are compensated for.

    Fitting a gain by least squares before comparing, rather than comparing raw waveforms directly,
    is what lets this scorer recognize a pair related by amplitude alone, by bit depth alone, or by
    both at once -- a depth change alone fits a gain near 1.0, and the confidence and evidence are
    identical either way. Trimming both to their common length before fitting is what lets it
    recognize a pair whose trailing-silence trim (``samplecore.waveform.trim_trailing_silence``)
    landed a few frames apart, without needing them to be pre-aligned by the caller. The ceiling
    compares against ``min(depth_a, depth_b)``, the lower-fidelity side's noise floor, since that
    dominates the residual regardless of which side it is on.

    Returns:
        None: when the two waveforms' lengths disagree by more than ``MAX_TRIM_MISMATCH_FRAMES``,
            when the shared-length ``waveform_a`` is silent, leaving the gain undefined, or when the
            best-fitting gain falls outside ``[MINIMUM_GAIN, MAXIMUM_GAIN]`` in magnitude -- each
            indicating a candidate pair whose fit is degenerate rather than a real match.
    """
    if abs(waveform_a.shape[0] - waveform_b.shape[0]) > MAX_TRIM_MISMATCH_FRAMES:
        return None

    common_length = min(waveform_a.shape[0], waveform_b.shape[0])
    trimmed_a, trimmed_b = waveform_a[:common_length], waveform_b[:common_length]

    reference_energy = float(np.sum(trimmed_a**2))
    if reference_energy == 0.0:
        return None

    gain = float(np.sum(trimmed_a * trimmed_b) / reference_energy)
    if not MINIMUM_GAIN <= abs(gain) <= MAXIMUM_GAIN:
        return None

    residual = trimmed_b - gain * trimmed_a
    rms_error = float(np.sqrt(np.mean(residual**2)))
    ceiling = _gain_variant_ceiling(min(depth_a, depth_b))
    confidence = max(0.0, 1.0 - rms_error / ceiling)
    return RelationScore(
        confidence=confidence,
        evidence={"gain": gain, "rms_error": rms_error, "max_abs_error": float(np.max(np.abs(residual)))},
    )


def score_resampled_variant(waveform_a: NDArray[np.float64], waveform_b: NDArray[np.float64]) -> RelationScore | None:
    """How closely a shorter waveform, resampled up and best-aligned, matches a longer one.

    Pearson correlation is exactly invariant to a positive gain applied to either waveform (it is
    computed on mean-centered, self-normalized signals), so this already recognizes a pair related by
    resampling and amplitude at once without any gain compensation of its own; the best-fitting gain
    is still recovered and reported in ``evidence``, purely as corroborating detail. Returns None
    when every offset in the search window leaves one of the compared windows silent (zero
    variance), since Pearson correlation is undefined there rather than meaningfully zero. Clamped to
    at most 1.0, since floating-point rounding on a near-perfect match can otherwise put the raw
    correlation a fraction above its mathematical ceiling.
    """
    short, long_ = (waveform_a, waveform_b) if waveform_a.shape[0] <= waveform_b.shape[0] else (waveform_b, waveform_a)
    ratio = Fraction(long_.shape[0], short.shape[0]).limit_denominator(MAX_RESAMPLE_DENOMINATOR)
    resampled = _match_length(resample_poly(short, up=ratio.numerator, down=ratio.denominator, axis=0), long_.shape[0])

    # A polyphase filter sized to the resampling ratio's denominator dominates resample_poly's own
    # cost far more than either waveform's length does, so MAX_RESAMPLE_DENOMINATOR is bounded
    # tightly (200 -- 0.5% ratio precision, already far finer than audio content needs) rather than
    # for the sake of ratio fidelity alone. The lag search below is the other real cost driver, and
    # it does scale with length, so it runs over at most MAX_COMPARISON_FRAMES of content -- enough
    # to confirm or reject a match confidently without paying for a candidate pair's full duration.
    comparison_length = min(resampled.shape[0], MAX_COMPARISON_FRAMES)
    aligned = _best_aligned_correlation(
        resampled[:comparison_length], long_[:comparison_length], max_lag=MAX_TRIM_LAG_FRAMES
    )
    if aligned is None:
        return None

    gain = float(
        np.sum(aligned.windowed_resampled * aligned.windowed_reference) / np.sum(aligned.windowed_resampled**2)
    )
    return RelationScore(
        confidence=min(1.0, max(0.0, aligned.correlation)),
        evidence={
            "correlation": aligned.correlation,
            "resample_ratio": long_.shape[0] / short.shape[0],
            "lag_frames": float(aligned.lag_frames),
            "gain": gain,
        },
    )


def _match_length(waveform: NDArray[np.float64], target_frames: int) -> NDArray[np.float64]:
    """Trims or zero-pads a resampled waveform to an exact frame count.

    A bounded-denominator resampling ratio is a close approximation of the true one, not an exact
    one, so the resampled length can land a handful of frames short or long of the target.
    """
    if waveform.shape[0] == target_frames:
        return waveform
    if waveform.shape[0] > target_frames:
        return waveform[:target_frames]

    return np.pad(waveform, ((0, target_frames - waveform.shape[0]), (0, 0)))


def _aligned_windows(
    resampled: NDArray[np.float64], reference: NDArray[np.float64], *, lag: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    """The overlapping windows of two equal-length waveforms once `reference` is shifted by `lag`.

    A positive lag skips that many frames from the start of `reference` to line it up with
    `resampled`'s own unshifted start -- the case where `reference` carries extra lead-in
    `resampled` does not; a negative lag is the opposite case. Returns None when the requested lag
    leaves no overlap at all -- checked explicitly here rather than trusting the frame count to
    always exceed the lag.
    """
    frame_count = resampled.shape[0]
    overlap = frame_count - abs(lag)
    if overlap <= 0:
        return None

    if lag >= 0:
        return resampled[:overlap], reference[lag : lag + overlap]

    return resampled[-lag : -lag + overlap], reference[:overlap]


@dataclass(frozen=True)
class _Alignment:
    """The best lag found between two waveforms, and the overlapping windows it lines up."""

    correlation: float
    lag_frames: int
    windowed_resampled: NDArray[np.float64]
    windowed_reference: NDArray[np.float64]


def _best_aligned_correlation(
    resampled: NDArray[np.float64], reference: NDArray[np.float64], *, max_lag: int
) -> _Alignment | None:
    """The highest Pearson correlation between the two waveforms across a bounded lag search.

    Searching a small window around zero absorbs the handful of frames of trim difference two
    independent exports of the same content commonly carry, without needing either one already
    aligned to the other.
    """
    best: _Alignment | None = None
    for lag in range(-max_lag, max_lag + 1):
        windows = _aligned_windows(resampled, reference, lag=lag)
        if windows is None:
            continue

        correlation = _pearson_correlation(*windows)
        if correlation is not None and (best is None or correlation > best.correlation):
            best = _Alignment(
                correlation=correlation, lag_frames=lag, windowed_resampled=windows[0], windowed_reference=windows[1]
            )

    return best


def _pearson_correlation(first: NDArray[np.float64], second: NDArray[np.float64]) -> float | None:
    first_centered = first.reshape(-1)
    first_centered = first_centered - first_centered.mean()
    second_centered = second.reshape(-1)
    second_centered = second_centered - second_centered.mean()
    denominator = np.sqrt(np.sum(first_centered**2) * np.sum(second_centered**2))
    if denominator == 0.0:
        return None

    return float(np.sum(first_centered * second_centered) / denominator)
