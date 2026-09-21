from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.settings import TransportSettings

QUANTILES_PER_FRAME: Final[int] = 4
GUARD_SHARE_OF_SHORTER_LENGTH: Final[float] = 0.25


@dataclass(frozen=True)
class TimeMap:
    """Where every output frame reads its two sources.

    Positions are fractional source frames, and a rate is how many source frames one output frame
    spans there, which is how wide a reading has to average. Shapes: every array is ``(output frames,)``.
    """

    sample_count: int
    first_positions: NDArray[np.float64]
    second_positions: NDArray[np.float64]
    first_rates: NDArray[np.float64]
    second_rates: NDArray[np.float64]

    @property
    def frame_count(self) -> int:
        return int(self.first_positions.shape[0])


@dataclass(frozen=True)
class _Landmarks:
    """One timeline cut at its onset: what comes before the guard, the guard itself, and the body after it."""

    onset: float
    pre_guard: float
    post_guard: float
    length: float

    @property
    def guard_start(self) -> float:
        return self.onset - self.pre_guard

    @property
    def body_start(self) -> float:
        return self.onset + self.post_guard

    @property
    def body_length(self) -> float:
        return max(self.length - self.body_start, 0.0)


@dataclass(frozen=True)
class _Timeline:
    """A timeline's landmarks beside the share of its body's length each quantile of the body's mass has passed."""

    landmarks: _Landmarks
    body_quantiles: NDArray[np.float64]


def interpolated_sample_count(first: int, second: int, *, weight: float) -> int:
    """The length a point between two sounds lasts: the geometric path between their lengths."""
    return max(int(round(float(np.exp((1.0 - weight) * np.log(first) + weight * np.log(second))))), 1)


def build_time_map(
    first: TransportAnalysis,
    second: TransportAnalysis,
    *,
    weight: float,
    hop_length: int,
    settings: TransportSettings,
) -> TimeMap:
    """Align two sounds in time at `weight` between them.

    Each timeline is cut at its onset. Around the onset both sources are read at their own rate, so
    an attack stays single and as sharp as it was; before it, time runs linearly from the start. After
    it, each body is read through the quantiles of its own mass over time, and the output body follows
    the straight line between the two sets of quantiles: the moment that has passed a given share of
    one sound's body meets the moment that has passed the same share of the other's. A share of every
    body's mass is spread evenly, which keeps both maps strictly increasing and bounds how slowly
    either source is read. The onset sits at the interpolated share of the length, and the length
    follows `interpolated_sample_count`.
    """
    sample_count = interpolated_sample_count(first.sample_count, second.sample_count, weight=weight)
    output_times = np.arange(1 + sample_count // hop_length, dtype=np.float64) * hop_length
    pre_guard = float(settings.onset_guard_frames * hop_length)
    shorter = min(first.sample_count, second.sample_count)
    post_guard = min(pre_guard, float(int(shorter * GUARD_SHARE_OF_SHORTER_LENGTH) // hop_length * hop_length))
    onset_share = (1.0 - weight) * first.onset_sample / first.sample_count + (
        weight * second.onset_sample / second.sample_count
    )
    first_landmarks = _Landmarks(first.onset_sample, pre_guard, post_guard, first.sample_count)
    second_landmarks = _Landmarks(second.onset_sample, pre_guard, post_guard, second.sample_count)
    output_landmarks = _Landmarks(onset_share * sample_count, pre_guard, post_guard, sample_count)
    quantile_grid = np.linspace(0.0, 1.0, QUANTILES_PER_FRAME * max(first.frame_count, second.frame_count) + 1)
    first_timeline = _Timeline(
        landmarks=first_landmarks,
        body_quantiles=_body_quantiles(
            first, landmarks=first_landmarks, quantile_grid=quantile_grid, hop_length=hop_length, settings=settings
        ),
    )
    second_timeline = _Timeline(
        landmarks=second_landmarks,
        body_quantiles=_body_quantiles(
            second, landmarks=second_landmarks, quantile_grid=quantile_grid, hop_length=hop_length, settings=settings
        ),
    )
    output_timeline = _Timeline(
        landmarks=output_landmarks,
        body_quantiles=(1.0 - weight) * first_timeline.body_quantiles + weight * second_timeline.body_quantiles,
    )
    first_positions = (
        _source_times(output_times, output=output_timeline, source=first_timeline, quantile_grid=quantile_grid)
        / hop_length
    )
    second_positions = (
        _source_times(output_times, output=output_timeline, source=second_timeline, quantile_grid=quantile_grid)
        / hop_length
    )
    return TimeMap(
        sample_count=sample_count,
        first_positions=first_positions,
        second_positions=second_positions,
        first_rates=_local_rates(first_positions),
        second_rates=_local_rates(second_positions),
    )


def _body_quantiles(
    analysis: TransportAnalysis,
    *,
    landmarks: _Landmarks,
    quantile_grid: NDArray[np.float64],
    hop_length: int,
    settings: TransportSettings,
) -> NDArray[np.float64]:
    """The share of the body's length by which each quantile of its mass has passed."""
    first_frame = int(np.ceil(landmarks.body_start / hop_length))
    last_frame = min(analysis.frame_count - 1, int((landmarks.body_start + landmarks.body_length) // hop_length))
    energies = analysis.frame_energy[first_frame : last_frame + 1].astype(np.float64)
    if landmarks.body_length <= 0.0 or energies.size == 0:
        return quantile_grid.copy()

    gate = analysis.peak_frame_energy * 10.0 ** (-settings.density_gate_db / 10.0)
    density = np.where(energies >= gate, energies**settings.density_exponent, 0.0)
    total = float(density.sum())
    shares = density / total if total > 0.0 else np.full(energies.size, 1.0 / energies.size)
    mixed = (1.0 - settings.uniform_share) * shares + settings.uniform_share / energies.size
    cumulative = np.concatenate(([0.0], np.cumsum(mixed)))
    cumulative[-1] = 1.0
    quantiles: NDArray[np.float64] = np.interp(quantile_grid, cumulative, np.linspace(0.0, 1.0, energies.size + 1))
    return quantiles


def _source_times(
    output_times: NDArray[np.float64],
    *,
    output: _Timeline,
    source: _Timeline,
    quantile_grid: NDArray[np.float64],
) -> NDArray[np.float64]:
    """The source time, in samples, each output time reads."""
    output_marks = output.landmarks
    source_marks = source.landmarks
    times = np.empty_like(output_times)
    before = output_times < output_marks.guard_start
    body = output_times >= output_marks.body_start
    within = ~before & ~body

    both_before = output_marks.guard_start > 0.0 and source_marks.guard_start > 0.0
    before_rate = source_marks.guard_start / output_marks.guard_start if both_before else 1.0
    times[before] = source_marks.guard_start - (output_marks.guard_start - output_times[before]) * before_rate
    times[within] = source_marks.onset + (output_times[within] - output_marks.onset)
    if output_marks.body_length > 0.0:
        shares = np.clip((output_times[body] - output_marks.body_start) / output_marks.body_length, 0.0, 1.0)
        quantiles = np.interp(shares, output.body_quantiles, quantile_grid)
        times[body] = (
            source_marks.body_start
            + np.interp(quantiles, quantile_grid, source.body_quantiles) * source_marks.body_length
        )
    else:
        times[body] = source_marks.body_start + (output_times[body] - output_marks.body_start)
    return times


def _local_rates(positions: NDArray[np.float64]) -> NDArray[np.float64]:
    if positions.shape[0] < 2:
        return np.ones_like(positions)
    rates: NDArray[np.float64] = np.abs(np.gradient(positions))
    return rates
