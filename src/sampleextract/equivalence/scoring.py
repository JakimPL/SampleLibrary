from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly

BIT_DEPTH_RMS_ERROR_CEILING: Final[float] = 0.02
BIT_DEPTH_MINIMUM_CONFIDENCE: Final[float] = 0.5

MAX_RESAMPLE_DENOMINATOR: Final[int] = 200
MAX_TRIM_LAG_FRAMES: Final[int] = 64
MAX_COMPARISON_FRAMES: Final[int] = 20_000
RESAMPLED_MINIMUM_CONFIDENCE: Final[float] = 0.9


@dataclass(frozen=True)
class RelationScore:
    """A detector's verdict on one candidate pair: how confident, and the evidence backing it."""

    confidence: float
    evidence: dict[str, float]


def score_bit_depth_variant(waveform_a: NDArray[np.float64], waveform_b: NDArray[np.float64]) -> RelationScore:
    """How closely two equal-shape waveforms match, evidenced against 8-bit quantisation noise.

    The ceiling is set to roughly eight times a full-scale 8-bit uniform quantiser's own
    theoretical root-mean-square noise (about 0.0023), giving headroom for rounding-convention
    differences between two independent quantisations of the same source while staying far below
    the error two genuinely different waveforms would show.
    """
    difference = waveform_a - waveform_b
    rms_error = float(np.sqrt(np.mean(difference**2)))
    confidence = max(0.0, 1.0 - rms_error / BIT_DEPTH_RMS_ERROR_CEILING)
    return RelationScore(
        confidence=confidence,
        evidence={"rms_error": rms_error, "max_abs_error": float(np.max(np.abs(difference)))},
    )


def score_resampled_variant(waveform_a: NDArray[np.float64], waveform_b: NDArray[np.float64]) -> RelationScore | None:
    """How closely a shorter waveform, resampled up and best-aligned, matches a longer one.

    Returns None when every offset in the search window leaves one of the compared windows
    silent (zero variance), since Pearson correlation is undefined there rather than
    meaningfully zero.
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

    correlation, lag_frames = aligned
    return RelationScore(
        confidence=max(0.0, correlation),
        evidence={
            "correlation": correlation,
            "resample_ratio": long_.shape[0] / short.shape[0],
            "lag_frames": float(lag_frames),
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


def _best_aligned_correlation(
    resampled: NDArray[np.float64], reference: NDArray[np.float64], *, max_lag: int
) -> tuple[float, int] | None:
    """The highest Pearson correlation between the two waveforms across a bounded lag search.

    A positive lag skips that many frames from the start of `reference` to line it up with
    `resampled`'s own unshifted start -- the case where `reference` carries extra lead-in
    `resampled` does not; a negative lag is the opposite case. Searching a small window around
    zero absorbs the handful of frames of trim difference two independent exports of the same
    content commonly carry, without needing either one already aligned to the other.
    """
    frame_count = resampled.shape[0]
    best_correlation: float | None = None
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        # A slice stop computed as frame_count - lag (or frame_count + lag) would, if negative,
        # index from the array's end rather than yield the intended empty window -- checked
        # explicitly here rather than trusting frame_count to always exceed max_lag.
        overlap = frame_count - abs(lag)
        if overlap <= 0:
            continue

        if lag >= 0:
            windowed_resampled = resampled[:overlap]
            windowed_reference = reference[lag : lag + overlap]
        else:
            windowed_resampled = resampled[-lag : -lag + overlap]
            windowed_reference = reference[:overlap]

        correlation = _pearson_correlation(windowed_resampled, windowed_reference)
        if correlation is not None and (best_correlation is None or correlation > best_correlation):
            best_correlation = correlation
            best_lag = lag

    return (best_correlation, best_lag) if best_correlation is not None else None


def _pearson_correlation(first: NDArray[np.float64], second: NDArray[np.float64]) -> float | None:
    first_centered = first.reshape(-1)
    first_centered = first_centered - first_centered.mean()
    second_centered = second.reshape(-1)
    second_centered = second_centered - second_centered.mean()
    denominator = np.sqrt(np.sum(first_centered**2) * np.sum(second_centered**2))
    if denominator == 0.0:
        return None

    return float(np.sum(first_centered * second_centered) / denominator)
