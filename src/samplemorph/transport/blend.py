from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.frame_reading import read_frames
from samplemorph.transport.morph import FIRST_END_WEIGHT, SECOND_END_WEIGHT, TransportedSpectrogram, heard_as_analyzed
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import interpolated_sample_count


def blend(
    first: TransportAnalysis,
    second: TransportAnalysis,
    *,
    weight: float,
    geometry: LogFrequencyGeometry,
    settings: TransportSettings,
) -> TransportedSpectrogram:
    """The crossfade a transport is judged against, on the same analyses.

    Both sounds are read at the same share of their lengths and blended bin by bin in decibels under
    their own peaks, the peaks meeting geometrically: the morph a straight line through a decibel
    grid makes, heard at the fidelity of the analyses themselves. Beside a transport it separates
    what moving features adds from what the analyses' fidelity adds.

    Raises:
        ValueError: the weight lies outside ``[0, 1]``.
    """
    if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
        raise ValueError(f"a blend runs between weights 0 and 1, got {weight}")
    if weight == FIRST_END_WEIGHT:
        return heard_as_analyzed(first)
    if weight == SECOND_END_WEIGHT:
        return heard_as_analyzed(second)

    sample_count = interpolated_sample_count(first.sample_count, second.sample_count, weight=weight)
    frame_count = 1 + sample_count // geometry.hop_length
    first_decibels, first_peak = _decibels_under_peak(
        _read_at_shares(first, frame_count=frame_count, settings=settings), dynamic_range_db=geometry.dynamic_range_db
    )
    second_decibels, second_peak = _decibels_under_peak(
        _read_at_shares(second, frame_count=frame_count, settings=settings), dynamic_range_db=geometry.dynamic_range_db
    )
    peak = first_peak ** (1.0 - weight) * second_peak**weight
    energy = peak * 10.0 ** (((1.0 - weight) * first_decibels + weight * second_decibels) / 10.0)
    return TransportedSpectrogram(magnitude=np.sqrt(energy).astype(np.float32), sample_count=sample_count)


def _read_at_shares(
    analysis: TransportAnalysis, *, frame_count: int, settings: TransportSettings
) -> NDArray[np.float32]:
    span = max(frame_count - 1, 1)
    rate = (analysis.frame_count - 1) / span
    positions = np.arange(frame_count, dtype=np.float64) * rate
    return read_frames(
        analysis.energy,
        positions=positions,
        rates=np.full(frame_count, rate),
        maximum_half_width=settings.maximum_reading_half_width,
    )


def _decibels_under_peak(energy: NDArray[np.float32], *, dynamic_range_db: float) -> tuple[NDArray[np.float64], float]:
    peak = max(float(energy.max()), float(np.finfo(np.float32).tiny))
    floor = peak * 10.0 ** (-dynamic_range_db / 10.0)
    decibels: NDArray[np.float64] = 10.0 * np.log10(np.maximum(energy.astype(np.float64), floor) / peak)
    return decibels, peak
