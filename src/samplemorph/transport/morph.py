from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.frame_reading import read_frames
from samplemorph.transport.levels import level_path
from samplemorph.transport.placement import place_groups
from samplemorph.transport.plan import monotone_plan
from samplemorph.transport.segmentation import LOWEST_MOVED_BIN, SpectralGroups, segment_spectrum
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import TimeMap, build_time_map

FIRST_END_WEIGHT: Final[float] = 0.0
SECOND_END_WEIGHT: Final[float] = 1.0


@dataclass(frozen=True)
class TransportedSpectrogram:
    """A magnitude between two sounds, bins by frames, with the length in samples it sounds for."""

    magnitude: NDArray[np.float32]
    sample_count: int


@dataclass(frozen=True)
class _ReadFrame:
    """One source frame as the transport reads it: its shape with unit sum, the outline that cuts it, and its energy."""

    shape: NDArray[np.float64]
    outline: NDArray[np.float64]
    level: float


def transport(
    first: TransportAnalysis,
    second: TransportAnalysis,
    *,
    weight: float,
    geometry: LogFrequencyGeometry,
    settings: TransportSettings,
) -> TransportedSpectrogram:
    """The magnitude `weight` of the way from one sound to another, every feature carried along its own path.

    Time is aligned by `build_time_map`. Each output frame then reads both sources where the map
    points, cuts both spectra into groups, pairs their mass in frequency order, and carries every
    paired piece to the geometric point between its two group centers: a partial glides from one
    pitch to the other, a resonance or a band of noise slides with it, and each end's shape fades
    out as it travels while the other's fades in. The frame's energy follows `level_path`. At weight
    0 and 1 the result is each sound's own analysis.

    Raises:
        ValueError: the weight lies outside ``[0, 1]``.
    """
    if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
        raise ValueError(f"a transport runs between weights 0 and 1, got {weight}")
    if weight == FIRST_END_WEIGHT:
        return heard_as_analyzed(first)
    if weight == SECOND_END_WEIGHT:
        return heard_as_analyzed(second)

    return transport_along(
        first,
        second,
        time_map=build_time_map(first, second, weight=weight, hop_length=geometry.hop_length, settings=settings),
        weight=weight,
        settings=settings,
    )


def transport_along(
    first: TransportAnalysis,
    second: TransportAnalysis,
    *,
    time_map: TimeMap,
    weight: float,
    settings: TransportSettings,
) -> TransportedSpectrogram:
    """The magnitude `weight` of the way between two analyses read along a time map already built.

    A morph that aligns two sounds by more than their spectra, and carries part of them by some other
    means, builds the map once on whatever it aligns and sends the rest of both sounds along it here.
    """
    first_energy, first_outline = _read_along(
        first, positions=time_map.first_positions, rates=time_map.first_rates, settings=settings
    )
    second_energy, second_outline = _read_along(
        second, positions=time_map.second_positions, rates=time_map.second_rates, settings=settings
    )
    magnitude = np.empty((first.energy.shape[0], time_map.frame_count), dtype=np.float32)
    for frame in range(time_map.frame_count):
        magnitude[:, frame] = _transported_frame(
            _read_frame(first_energy[:, frame], first_outline[:, frame], analysis=first, settings=settings),
            _read_frame(second_energy[:, frame], second_outline[:, frame], analysis=second, settings=settings),
            weight=weight,
            settings=settings,
        )
    return TransportedSpectrogram(magnitude=magnitude, sample_count=time_map.sample_count)


def heard_as_analyzed(analysis: TransportAnalysis) -> TransportedSpectrogram:
    """A sound's own magnitude and length, the transport's reading at either end."""
    return TransportedSpectrogram(magnitude=np.sqrt(analysis.energy), sample_count=analysis.sample_count)


def _read_along(
    analysis: TransportAnalysis,
    *,
    positions: NDArray[np.float64],
    rates: NDArray[np.float64],
    settings: TransportSettings,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    half_width = settings.maximum_reading_half_width
    return (
        read_frames(analysis.energy, positions=positions, rates=rates, maximum_half_width=half_width),
        read_frames(analysis.outline, positions=positions, rates=rates, maximum_half_width=half_width),
    )


def _read_frame(
    energy: NDArray[np.float32],
    outline: NDArray[np.float32],
    *,
    analysis: TransportAnalysis,
    settings: TransportSettings,
) -> _ReadFrame:
    """A frame's energy and outline as shapes with unit sum, each lifted by the sound's mean spectrum far under its loudest frame.

    The lift gives a silent frame the shape of its sound, so a sound fading to nothing still has
    somewhere for its pieces to travel from.
    """
    lift = analysis.peak_frame_energy * 10.0 ** (-settings.silent_shape_depth_db / 10.0)
    silent_shape = analysis.silent_shape.astype(np.float64)
    return _ReadFrame(
        shape=_lifted(energy.astype(np.float64), silent_shape=silent_shape, lift=lift),
        outline=_lifted(outline.astype(np.float64), silent_shape=silent_shape, lift=lift),
        level=float(energy.sum(dtype=np.float64)),
    )


def _lifted(values: NDArray[np.float64], *, silent_shape: NDArray[np.float64], lift: float) -> NDArray[np.float64]:
    total = float(values.sum()) + lift
    if total <= 0.0:
        return silent_shape
    lifted: NDArray[np.float64] = (values + lift * silent_shape) / total
    return lifted


def _transported_frame(
    first: _ReadFrame, second: _ReadFrame, *, weight: float, settings: TransportSettings
) -> NDArray[np.float32]:
    first_groups = segment_spectrum(first.shape, first.outline, prominence_db=settings.peak_prominence_db)
    second_groups = segment_spectrum(second.shape, second.outline, prominence_db=settings.peak_prominence_db)
    plan = monotone_plan(first_groups.group_energy, second_groups.group_energy)
    centers = np.exp(
        (1.0 - weight) * np.log(first_groups.group_center[plan.first_groups])
        + weight * np.log(second_groups.group_center[plan.second_groups])
    )
    shape = place_groups(
        first.shape,
        first_groups,
        piece_groups=plan.first_groups,
        piece_gains=_piece_gains(first_groups, piece_groups=plan.first_groups, masses=plan.masses, share=1.0 - weight),
        piece_scales=centers / first_groups.group_center[plan.first_groups],
    ) + place_groups(
        second.shape,
        second_groups,
        piece_groups=plan.second_groups,
        piece_gains=_piece_gains(second_groups, piece_groups=plan.second_groups, masses=plan.masses, share=weight),
        piece_scales=centers / second_groups.group_center[plan.second_groups],
    )
    shape[:LOWEST_MOVED_BIN] += (1.0 - weight) * first.shape[:LOWEST_MOVED_BIN] + (
        weight * second.shape[:LOWEST_MOVED_BIN]
    )
    level = level_path(first.level, second.level, weight=weight, exponent=settings.level_exponent)
    magnitude: NDArray[np.float32] = np.sqrt(level * shape).astype(np.float32)
    return magnitude


def _piece_gains(
    groups: SpectralGroups, *, piece_groups: NDArray[np.intp], masses: NDArray[np.float64], share: float
) -> NDArray[np.float64]:
    """The gain each piece deposits its group's grains at, one end's `share` of the frame.

    A piece carries the share of the whole spectrum the plan gave it, so a group split over several
    pieces sends the matching part of itself along each.
    """
    group_shares = groups.group_energy / groups.group_energy.sum()
    gains: NDArray[np.float64] = share * masses / group_shares[piece_groups]
    return gains
