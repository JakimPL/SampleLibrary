from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.measurement.comparison import held_out_distance_db, held_out_spectrum
from samplemorph.measurement.loudness import integrated_loudness, match_loudness
from samplemorph.measurement.modulation_spectrum import ModulationLobeDepths, modulation_lobe_depths
from samplemorph.measurement.morph_path.harmonicity import harmonicity
from samplemorph.measurement.morph_path.heard_partials import heard_partials
from samplemorph.measurement.morph_path.loudness_path import LoudnessPath
from samplemorph.measurement.morph_path.partial_wobble import partial_wobble_cents
from samplemorph.measurement.morph_path.spectra import (
    BlendFit,
    blend_fit,
    crest_factor_db,
    fraction_spectrum,
    mean_peak_count,
    mean_spectral_entropy,
    resolved_spectrum,
)
from samplemorph.measurement.readings import ReconstructionReadings, read_reconstruction
from samplemorph.partials.settings import NoteSettings


@dataclass(frozen=True)
class PathPoint:
    """One render along a path: the weight it stands at and the frames it made."""

    weight: float
    waveform: NDArray[np.float64]


@dataclass(frozen=True)
class HeardPath:
    """Every render one route made between two sounds, ends first and last, beside both sounds as heard in the pair's frame.

    Every waveform, the renders and both sounds alike, is played at `rate_hz`.
    """

    points: tuple[PathPoint, ...]
    first: NDArray[np.float64]
    second: NDArray[np.float64]
    rate_hz: float

    @property
    def weights(self) -> tuple[float, ...]:
        return tuple(point.weight for point in self.points)

    @property
    def sample_rate_hz(self) -> int:
        return int(round(self.rate_hz))


@dataclass(frozen=True)
class PointScreen:
    """What one point carries beyond the two ends it lies between, each reading held against the rendered ends.

    `peak_count_ratio` is the point's peaks over the count interpolated between the ends', which a
    dissolve reads near two. `spread_excess` is its spectral entropy over the wider end's, in nats.
    `crest_excess_db`, `fluctuation_excess` and `roughness_excess` are its crest factor and its
    modulation depths over the values interpolated between the ends', the readings that tracked
    a heard phase artifact on percussive and tonal material. `wobble_cents` is how far its partials
    move in pitch every 3 ms (`partial_wobble_cents`), and `wobble_excess_cents` that over the value
    interpolated between the ends, which a vibrato the ends lack reads above zero. `harmonicity` is
    the share of its partial energy standing on notes, which says whether what it holds still sounds
    like notes. A point or an end holding no partial reads not a number on all three.
    """

    peak_count_ratio: float
    spread_excess: float
    crest_excess_db: float
    fluctuation_excess: float
    roughness_excess: float
    wobble_cents: float
    wobble_excess_cents: float
    harmonicity: float


@dataclass(frozen=True)
class PointReadings:
    """Every reading taken on one point of a path.

    `blend` fits the point as a decibel crossfade of the rendered ends; the loudness offsets place
    it against the lines `LoudnessPath` draws between them.
    """

    weight: float
    blend: BlendFit
    loudness_lufs: float
    loudness_offset_lu: float
    sone_offset_lu: float
    screen: PointScreen


@dataclass(frozen=True)
class PathReadings:
    """A whole path's readings: what each end cost against the sound it renders, and every point along the way."""

    first_end: ReconstructionReadings
    second_end: ReconstructionReadings
    points: tuple[PointReadings, ...]
    largest_dip_lu: float


@dataclass(frozen=True)
class _PointFeatures:
    spectrum: NDArray[np.float64]
    peak_count: float
    entropy: float
    crest_db: float
    depths: ModulationLobeDepths
    wobble_cents: float
    harmonicity: float


def read_path(path: HeardPath) -> PathReadings:
    """Read a path's ends against the sounds they render and every point against the path's own ends.

    Holding each point against the rendered ends cancels what a route loses at every weight alike,
    so what remains is how it moves between the two.
    """
    features = tuple(_features(point.waveform, rate_hz=path.sample_rate_hz) for point in path.points)
    loudness = LoudnessPath(
        weights=path.weights,
        loudness_lufs=tuple(
            integrated_loudness(point.waveform, source_rate_hz=path.sample_rate_hz) for point in path.points
        ),
    )
    first, second = features[0], features[-1]
    points = tuple(
        PointReadings(
            weight=point.weight,
            blend=blend_fit(point_features.spectrum, first=first.spectrum, second=second.spectrum),
            loudness_lufs=loudness.loudness_lufs[index],
            loudness_offset_lu=loudness.line_offset_lu(index),
            sone_offset_lu=loudness.sone_offset_lu(index),
            screen=_screen(point_features, first=first, second=second, weight=point.weight),
        )
        for index, (point, point_features) in enumerate(zip(path.points, features, strict=True))
    )
    return PathReadings(
        first_end=_end_readings(path.points[0].waveform, path.first, rate_hz=path.sample_rate_hz),
        second_end=_end_readings(path.points[-1].waveform, path.second, rate_hz=path.sample_rate_hz),
        points=points,
        largest_dip_lu=loudness.largest_dip_lu,
    )


def transposition_distances_db(points: tuple[PathPoint, ...], references: tuple[PathPoint, ...]) -> tuple[float, ...]:
    """How far each point sits from its reference at the same weight, as held-out distance.

    For one sample heard at two rates, the reference at each weight is that sample heard at the
    rate between them, so a route that moves pitch and length as a retuning does reads near its
    own endpoint cost here.

    Raises:
        ValueError: a reference stands at another weight than the point it is paired with.
    """
    distances = []
    for point, reference in zip(points, references, strict=True):
        if point.weight != reference.weight:
            raise ValueError(f"a point at weight {point.weight} was paired with a reference at {reference.weight}")
        distances.append(held_out_distance_db(held_out_spectrum(reference.waveform), held_out_spectrum(point.waveform)))
    return tuple(distances)


def _features(waveform: NDArray[np.float64], *, rate_hz: int) -> _PointFeatures:
    resolved = resolved_spectrum(waveform)
    partials = heard_partials(waveform, rate_hz=float(rate_hz))
    return _PointFeatures(
        spectrum=fraction_spectrum(waveform),
        peak_count=mean_peak_count(resolved),
        entropy=mean_spectral_entropy(resolved),
        crest_db=crest_factor_db(waveform),
        depths=modulation_lobe_depths(waveform, source_rate_hz=rate_hz),
        wobble_cents=partial_wobble_cents(partials),
        harmonicity=harmonicity(partials, settings=NoteSettings()),
    )


def _screen(point: _PointFeatures, *, first: _PointFeatures, second: _PointFeatures, weight: float) -> PointScreen:
    def between(first_value: float, second_value: float) -> float:
        return (1.0 - weight) * first_value + weight * second_value

    expected_peaks = between(first.peak_count, second.peak_count)
    return PointScreen(
        peak_count_ratio=point.peak_count / expected_peaks if expected_peaks > 0.0 else float("nan"),
        spread_excess=point.entropy - max(first.entropy, second.entropy),
        crest_excess_db=point.crest_db - between(first.crest_db, second.crest_db),
        fluctuation_excess=point.depths.fluctuation - between(first.depths.fluctuation, second.depths.fluctuation),
        roughness_excess=point.depths.roughness - between(first.depths.roughness, second.depths.roughness),
        wobble_cents=point.wobble_cents,
        wobble_excess_cents=point.wobble_cents - between(first.wobble_cents, second.wobble_cents),
        harmonicity=point.harmonicity,
    )


def _end_readings(render: NDArray[np.float64], sound: NDArray[np.float64], *, rate_hz: int) -> ReconstructionReadings:
    """An end's render against the sound it renders, over the length both share, matched in loudness to the sound."""
    frames = min(render.shape[0], sound.shape[0])
    reference, matched = match_loudness(
        (sound[:frames], render[:frames]), reference=sound[:frames], source_rate_hz=rate_hz
    )
    return read_reconstruction(matched, reference, source_rate_hz=rate_hz)
