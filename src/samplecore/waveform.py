from __future__ import annotations

from fractions import Fraction
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from scipy.signal import resample_poly

from samplecore.models.base import FROZEN

DEFAULT_WAVEFORM_BUCKET_COUNT: Final[int] = 200
DEFAULT_THUMBNAIL_BUCKET_COUNT: Final[int] = 32
SEMITONES_PER_OCTAVE: Final[int] = 12
DEFAULT_RESAMPLING_DENOMINATOR: Final[int] = 200


class WaveformPeak(BaseModel):
    """One bucket's amplitude envelope in a compact waveform preview."""

    model_config = FROZEN

    minimum: float
    maximum: float


def fold_to_mono(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Average a waveform's channels into one, passing an already-mono signal through unchanged."""
    return waveform.mean(axis=1) if waveform.ndim > 1 else waveform


def remove_dc_offset(mono: NDArray[np.float64]) -> NDArray[np.float64]:
    """Subtract a mono signal's own mean, correcting a constant recording-chain bias.

    An off-center signal registers as spurious low-frequency energy in a spectral analysis and
    skews an RMS-based envelope reading; a signal already centered passes through unaffected, since
    its mean already sits at or near zero.
    """
    return mono - mono.mean()


def resample_by_semitones(
    waveform: NDArray[np.float64],
    *,
    semitones: float,
    maximum_denominator: int = DEFAULT_RESAMPLING_DENOMINATOR,
) -> NDArray[np.float64]:
    """Read a waveform as though its playback rate sat `semitones` above the rate it was stored at.

    This is what a tracker does when one instrument slot points at another slot's waveform: the
    same frames are read faster or slower, which raises the pitch and shortens the sound together.
    Positive semitones therefore return fewer frames than they were given, and negative semitones
    return more.

    The rate ratio is approached by a fraction of at most `maximum_denominator`, which keeps the
    polyphase resampler's filter a manageable length while landing within a thousandth of a
    semitone of the requested interval across the range this corpus retunes over.
    """
    ratio = Fraction(2.0 ** (-semitones / SEMITONES_PER_OCTAVE)).limit_denominator(maximum_denominator)
    resampled: NDArray[np.float64] = resample_poly(waveform, ratio.numerator, ratio.denominator, axis=0)
    return resampled


def resample_to_fraction_points(values: NDArray[np.float64], *, point_count: int, axis: int = 0) -> NDArray[np.float64]:
    """Resample a series indexed by analysis frame onto `point_count` points of duration fraction.

    Both the source and target positions span ``[0, 1]``, so the result describes the same content
    at a fixed resolution whatever the frame count was. This decouples a descriptor's or an image's
    output size from however many raw analysis frames a clip happens to produce -- a count that
    varies with the assumed sample rate and is a noisy estimate for a short clip -- so the same
    content read at two different rates lands on directly comparable output.

    `axis` selects which axis carries the frames; every other axis is preserved in place.
    """
    frame_count = values.shape[axis]
    source_fractions = np.linspace(0.0, 1.0, frame_count)
    target_fractions = np.linspace(0.0, 1.0, point_count)
    frames_last = np.moveaxis(values, axis, -1)
    resampled = np.stack(
        [np.interp(target_fractions, source_fractions, series) for series in frames_last.reshape(-1, frame_count)]
    )
    return np.moveaxis(resampled.reshape(*frames_last.shape[:-1], point_count), -1, axis)


def trim_trailing_silence(waveform: NDArray[np.float64], *, threshold: float) -> NDArray[np.float64]:
    """Removes trailing content at or below `threshold` amplitude, leaving the leading content untouched.

    Only the end is ever trimmed: leading silence audibly delays a sample's attack relative to when
    a tracker triggers it, a real difference rather than noise, while a genuinely null tail is the
    one difference two otherwise identical waveforms can carry that is no difference at all. A frame
    counts as content when any channel exceeds the threshold, so a signal present on only one
    channel of a multi-channel waveform is never trimmed away.
    """
    peak_per_frame = np.abs(waveform).max(axis=1)
    above_threshold = np.flatnonzero(peak_per_frame > threshold)
    if above_threshold.size == 0:
        return waveform[:0]

    return waveform[: int(above_threshold[-1]) + 1]


def compute_waveform_peaks(pcm: NDArray[np.float64], *, bucket_count: int) -> tuple[WaveformPeak, ...]:
    """Downsample a waveform's amplitude envelope into `bucket_count` min/max buckets.

    Multi-channel audio is mixed to mono first, matching the same `mean(axis=1)` pattern used
    for equivalence fingerprinting and cloud feature extraction, since a preview shows overall
    amplitude rather than per-channel detail. `bucket_count` is clamped to the frame count, so a
    sample shorter than the requested resolution still produces one bucket per frame.
    """
    mono = pcm.mean(axis=1)
    effective_bucket_count = min(bucket_count, mono.shape[0])
    buckets = np.array_split(mono, effective_bucket_count)
    return tuple(WaveformPeak(minimum=float(bucket.min()), maximum=float(bucket.max())) for bucket in buckets)
