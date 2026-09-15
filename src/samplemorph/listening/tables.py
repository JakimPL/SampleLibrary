from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from samplecore.tables import TableValue
from samplemorph.listening.pairs import CatalogPair, DrawnPair, RetunedPair
from samplemorph.measurement.morph_path.pitch_path import PitchPath
from samplemorph.measurement.morph_path.readings import PathReadings, PointReadings

MIDPOINT_WEIGHT: Final[float] = 0.5
UNREAD: Final[str] = ""

TableRow = dict[str, TableValue]


@dataclass(frozen=True)
class RenderTimings:
    """How long a route took to prepare both ends, and to render each point of the path, in seconds."""

    prepare_seconds: float
    render_seconds: tuple[float, ...]


@dataclass(frozen=True)
class RouteOnPair:
    """Everything one route's path over one pair read, for the tables.

    `pitch` is read on pairs of two pitched sounds alone, and `transposition_distances_db` holds a
    distance for each point strictly between the ends of a sample heard at two rates, and nothing
    for any other pair.
    """

    pair: DrawnPair
    folder: str
    frame_counts: tuple[int, ...]
    timings: RenderTimings
    readings: PathReadings
    pitch: PitchPath | None
    transposition_distances_db: tuple[float, ...]


def point_rows(run: RouteOnPair) -> list[TableRow]:
    """One row per point of the path: its render and every reading taken on it."""
    rows = []
    for index, point in enumerate(run.readings.points):
        rows.append(
            {
                "pair": run.pair.name,
                "route": run.folder,
                "weight": point.weight,
                "frames": run.frame_counts[index],
                "render_seconds": run.timings.render_seconds[index],
                **_point_values(point),
                "pitch_semitones": run.pitch.semitones[index] if run.pitch is not None else UNREAD,
                "pitch_deviation_semitones": (
                    run.pitch.deviation_semitones(index) if run.pitch is not None else UNREAD
                ),
                "transposition_distance_db": _transposition_at(run, index=index),
            }
        )
    return rows


def path_row(run: RouteOnPair) -> TableRow:
    """One row for the whole path: what each end cost, what the midpoint reads, and the path's own readings."""
    midpoint_index = min(
        range(len(run.readings.points)), key=lambda index: abs(run.readings.points[index].weight - MIDPOINT_WEIGHT)
    )
    midpoint = run.readings.points[midpoint_index]
    first_label, second_label = _labels(run.pair)
    return {
        "pair": run.pair.name,
        "kind": run.pair.kind,
        "route": run.folder,
        "first_label": first_label,
        "second_label": second_label,
        "prepare_seconds": run.timings.prepare_seconds,
        "median_render_seconds": sorted(run.timings.render_seconds)[len(run.timings.render_seconds) // 2],
        **{f"first_{name}": value for name, value in asdict(run.readings.first_end).items()},
        **{f"second_{name}": value for name, value in asdict(run.readings.second_end).items()},
        "largest_dip_lu": run.readings.largest_dip_lu,
        "pitch_jump_share": run.pitch.jump_share if run.pitch is not None else UNREAD,
        "largest_pitch_deviation_semitones": (
            run.pitch.largest_deviation_semitones if run.pitch is not None else UNREAD
        ),
        "midpoint_weight": midpoint.weight,
        **{f"midpoint_{name}": value for name, value in _point_values(midpoint).items()},
        "midpoint_transposition_distance_db": _transposition_at(run, index=midpoint_index),
    }


def verdict_rows(runs: tuple[RouteOnPair, ...]) -> list[TableRow]:
    """A blank verdict for every route on every pair, for the listener to fill in."""
    return [{"pair": run.pair.name, "route": run.folder, "verdict": UNREAD, "notes": UNREAD} for run in runs]


def _point_values(point: PointReadings) -> TableRow:
    return {
        "blend_weight": point.blend.weight,
        "blend_residual_db": point.blend.residual_db,
        "blend_residual_share": point.blend.residual_share,
        "loudness_lufs": point.loudness_lufs,
        "loudness_offset_lu": point.loudness_offset_lu,
        "sone_offset_lu": point.sone_offset_lu,
        **asdict(point.screen),
    }


def _labels(pair: DrawnPair) -> tuple[str, str]:
    match pair:
        case CatalogPair():
            return pair.first.label, pair.second.label
        case RetunedPair():
            return pair.sample.label, pair.sample.label


def _transposition_at(run: RouteOnPair, *, index: int) -> TableValue:
    """The transposition distance of the point at `index`, whose distances start at the first point after the first end."""
    interior_index = index - 1
    if not 0 <= interior_index < len(run.transposition_distances_db):
        return UNREAD
    return run.transposition_distances_db[interior_index]
