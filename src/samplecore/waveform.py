from __future__ import annotations

from fractions import Fraction
from functools import cache
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from scipy.signal import butter, buttord, resample_poly, sosfiltfilt

from samplecore.models.base import FROZEN
from samplecore.models.thumbnail import SampleThumbnail

DEFAULT_WAVEFORM_BUCKET_COUNT: Final[int] = 200
DEFAULT_THUMBNAIL_BUCKET_COUNT: Final[int] = 32
SEMITONES_PER_OCTAVE: Final[int] = 12
DEFAULT_RESAMPLING_DENOMINATOR: Final[int] = 200
SUBSONIC_PASSBAND_HZ: Final[float] = 30.0
SUBSONIC_STOPBAND_HZ: Final[float] = 10.0
SUBSONIC_PASSBAND_RIPPLE_DB: Final[float] = 1.0
SUBSONIC_STOPBAND_ATTENUATION_DB: Final[float] = 60.0
SUBSONIC_FILTER_PASSES: Final[int] = 2
SUBSONIC_SETTLE_PERIODS: Final[float] = 3.0


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


@cache
def subsonic_sections(sample_rate_hz: int) -> NDArray[np.float64]:
    """The second-order sections of the high-pass `remove_subsonic` applies at one sample rate.

    The order is solved for the shallowest Butterworth that holds `SUBSONIC_PASSBAND_HZ` within
    `SUBSONIC_PASSBAND_RIPPLE_DB` and pushes `SUBSONIC_STOPBAND_HZ` down by
    `SUBSONIC_STOPBAND_ATTENUATION_DB`, so the filter is as gentle as that specification allows at
    every rate it is designed for. The filter runs `SUBSONIC_FILTER_PASSES` times over a signal, so
    each pass is designed to its share of both figures and the two together meet them. Sections
    keep a cutoff this far below the rate numerically stable.
    """
    order, natural_frequency_hz = buttord(
        SUBSONIC_PASSBAND_HZ,
        SUBSONIC_STOPBAND_HZ,
        SUBSONIC_PASSBAND_RIPPLE_DB / SUBSONIC_FILTER_PASSES,
        SUBSONIC_STOPBAND_ATTENUATION_DB / SUBSONIC_FILTER_PASSES,
        fs=sample_rate_hz,
    )
    sections: NDArray[np.float64] = butter(
        order, natural_frequency_hz, btype="highpass", output="sos", fs=sample_rate_hz
    )
    return sections


def remove_subsonic(mono: NDArray[np.float64], *, sample_rate_hz: int) -> NDArray[np.float64]:
    """Keep the band a listener hears from a mono signal, removing the rumble and offset below it.

    The filter runs forward and then back over the signal, so every frequency keeps its timing and
    a transient's onset stays where it was. Each pass settles over an extension of
    `SUBSONIC_SETTLE_PERIODS` cutoff periods at either end that mirrors the signal within its own
    range of values, so a signal that starts or stops mid-cycle keeps its edges: the extension
    carries the same level the signal does, which is what lets a high-pass settle there quietly. It
    is designed at `sample_rate_hz`, the rate the frames are read at: a sample stored at the nominal
    container rate and heard above it sees the cutoff scale up by the same ratio, which keeps the
    cutoff conservative for tracker material, whose heard rates sit at or below the container rate.
    A signal shorter than the settling span is read with the extension it can afford.
    """
    settle_length = min(int(SUBSONIC_SETTLE_PERIODS * sample_rate_hz / SUBSONIC_PASSBAND_HZ), mono.shape[0] - 1)
    filtered: NDArray[np.float64] = sosfiltfilt(
        subsonic_sections(sample_rate_hz), mono, padtype="even", padlen=settle_length
    )
    return filtered


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


def heard_at_rate(
    waveform: NDArray[np.float64], *, playback_rate_hz: float, stored_rate_hz: float
) -> NDArray[np.float64]:
    """Read a waveform stored at one rate as a listener hears it played at another.

    A tracker plays the stored frames at the sample's own rate, so a sample played below the rate
    its file states sounds lower and lasts longer than the file alone says. The frames come back
    as they sound at `stored_rate_hz`, which is what a model reading the file's rate then hears.
    """
    semitones = SEMITONES_PER_OCTAVE * float(np.log2(playback_rate_hz / stored_rate_hz))
    return resample_by_semitones(waveform, semitones=semitones)


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


def triangular_weights(
    *,
    source_positions: NDArray[np.float64],
    target_positions: NDArray[np.float64],
    half_widths: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Weights averaging a series read at `source_positions` onto each of `target_positions`.

    Each target draws on the sources within its own half-width, weighted linearly from its center
    down to its edge and summing to one. A target covering many sources averages across them, and
    one landing between two sources interpolates between them, so the same rule serves a series
    read onto fewer points and onto more. Every half-width covers at least the source spacing, so
    each target draws on the series it reads from.
    """
    distance = np.abs(source_positions[None, :] - target_positions[:, None])
    weights = np.clip(1.0 - distance / half_widths[:, None], 0.0, None)
    normalized: NDArray[np.float64] = weights / weights.sum(axis=1, keepdims=True)
    return normalized


def average_to_fraction_points(values: NDArray[np.float64], *, point_count: int, axis: int = 0) -> NDArray[np.float64]:
    """Resample a series onto `point_count` points of duration fraction, averaging across each span.

    Like `resample_to_fraction_points`, both source and target positions span ``[0, 1]``, so the
    result describes the same content at a fixed resolution whatever the frame count was. Each
    output point averages the input across the span it stands for, so a series read onto fewer
    points carries the whole of what those points cover -- which holds a spectrogram's frames in
    the time order the analysis found them.

    `axis` selects which axis carries the frames; every other axis is preserved in place. A series
    of one frame is that frame throughout, since one reading covers the whole span.
    """
    frame_count = values.shape[axis]
    if frame_count == 1:
        return np.repeat(values, point_count, axis=axis)
    source_positions = np.linspace(0.0, 1.0, frame_count)
    target_positions = np.linspace(0.0, 1.0, point_count)
    source_spacing = 1.0 / max(frame_count - 1, 1)
    target_spacing = 1.0 / max(point_count - 1, 1)
    half_widths = np.full(point_count, max(target_spacing, source_spacing))
    weights = triangular_weights(
        source_positions=source_positions, target_positions=target_positions, half_widths=half_widths
    )
    frames_last = np.moveaxis(values, axis, -1)
    averaged = frames_last.reshape(-1, frame_count) @ weights.T
    return np.moveaxis(averaged.reshape(*frames_last.shape[:-1], point_count), -1, axis)


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


def compute_thumbnail(sample_hash: str, pcm: NDArray[np.float64]) -> SampleThumbnail:
    """The waveform preview every listing shows for a sample, at the library's thumbnail resolution."""
    peaks = compute_waveform_peaks(pcm, bucket_count=DEFAULT_THUMBNAIL_BUCKET_COUNT)
    return SampleThumbnail(
        sample_hash=sample_hash,
        bucket_count=len(peaks),
        minimums=tuple(peak.minimum for peak in peaks),
        maximums=tuple(peak.maximum for peak in peaks),
    )
