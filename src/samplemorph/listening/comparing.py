from __future__ import annotations

import json
import logging
import string
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import JsonValue

from samplecore.tables import write_table
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.listening.heard_pairs import HeardPair, OriginalSound
from samplemorph.listening.pairs import PairSet, pair_set_digest
from samplemorph.listening.tables import RenderTimings, RouteOnPair, path_row, point_rows, verdict_rows
from samplemorph.measurement.morph_path.pitch_path import PitchPath, heard_pitch, is_pitched_pair
from samplemorph.measurement.morph_path.readings import (
    HeardPath,
    PathPoint,
    read_path,
    transposition_distances_db,
)
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME
from samplemorph.rendering import RENDER_REVISION, RenderedFile, RenderKind, write_rendering
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.named import NamedRoute
from samplemorph.routes.route import PreparedPair

PATH_WEIGHT_COUNT: Final[int] = 9
DEFAULT_PATH_WEIGHTS: Final[tuple[float, ...]] = tuple(
    index / (PATH_WEIGHT_COUNT - 1) for index in range(PATH_WEIGHT_COUNT)
)
DEFAULT_LISTENING_WEIGHTS: Final[tuple[float, ...]] = (0.25, 0.5, 0.75)
PATH_GAP_SECONDS: Final[float] = 0.15
READINGS_FILE_NAME: Final[str] = "readings.csv"
PATHS_FILE_NAME: Final[str] = "paths.csv"
VERDICTS_FILE_NAME: Final[str] = "verdicts.csv"
MANIFEST_FILE_NAME: Final[str] = "manifest.json"
PATH_FILE_NAME: Final[str] = "path.wav"
FIRST_ORIGINAL_FILE_NAME: Final[str] = "original_first.wav"
SECOND_ORIGINAL_FILE_NAME: Final[str] = "original_second.wav"
FIRST_END_WEIGHT: Final[float] = 0.0
SECOND_END_WEIGHT: Final[float] = 1.0
PERCENT: Final[int] = 100

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComparedRoute:
    """One route a comparison renders, and the folder its files go under: the route's own name, or a letter dealt blind."""

    named: NamedRoute
    folder: str


@dataclass(frozen=True)
class ComparisonWeights:
    """The weights every path is rendered and read at, and those among them written as files to listen to.

    Raises:
        ValueError: the path weights do not rise from 0 to 1, or a listening weight is not a path weight.
    """

    path: tuple[float, ...]
    listening: tuple[float, ...]

    def __post_init__(self) -> None:
        rising = all(earlier < later for earlier, later in zip(self.path, self.path[1:]))
        if len(self.path) < 2 or self.path[0] != FIRST_END_WEIGHT or self.path[-1] != SECOND_END_WEIGHT or not rising:
            raise ValueError(f"path weights rise from 0 to 1, got {self.path}")
        missing = sorted(set(self.listening) - set(self.path))
        if missing:
            raise ValueError(f"every listening weight is a path weight, and {missing} are not")

    @property
    def written(self) -> frozenset[float]:
        """The weights written as files: both ends and every listening weight."""
        return frozenset((FIRST_END_WEIGHT, SECOND_END_WEIGHT, *self.listening))


@dataclass(frozen=True)
class ComparisonSummary:
    """What a comparison wrote: how many pairs, through how many routes, into which directory."""

    pair_count: int
    route_count: int
    output_directory: Path


def blind_folders(names: tuple[str, ...], *, random_seed: int) -> tuple[str, ...]:
    """Every route's files under a letter, dealt in seeded order, so a listener hears the routes by letter alone."""
    order = np.random.default_rng(random_seed).permutation(len(names))
    return tuple(string.ascii_uppercase[int(position)] for position in order)


def compare_routes(
    heard_pairs: tuple[HeardPair, ...],
    *,
    pair_set: PairSet,
    routes: tuple[ComparedRoute, ...],
    weights: ComparisonWeights,
    output_directory: Path,
) -> ComparisonSummary:
    """Render every pair through every route, write what a listener needs, and read every path.

    Each pair gets a folder holding both originals at their own rates, and a folder per route
    holding both ends and every listening weight, one file each, beside ``path.wav``: every path
    weight in order, a short silence apart. Files keep the level they were rendered at. The
    readings go to ``readings.csv``, one row per point, and ``paths.csv``, one row per path;
    ``verdicts.csv`` waits for the listener, and ``manifest.json``, written first, names the routes,
    the weights and the pairs. The tables are written again after every pair, so they hold every
    pair rendered so far.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / MANIFEST_FILE_NAME).write_text(
        json.dumps(_manifest(pair_set, routes=routes, weights=weights), indent=2), encoding="utf-8"
    )
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    runs: list[RouteOnPair] = []
    for heard in heard_pairs:
        pair = heard.pair
        pair_directory = output_directory / pair.name
        _write_original(pair_directory / FIRST_ORIGINAL_FILE_NAME, heard.first_original, weight=FIRST_END_WEIGHT)
        _write_original(pair_directory / SECOND_ORIGINAL_FILE_NAME, heard.second_original, weight=SECOND_END_WEIGHT)
        pitched = is_pitched_pair(
            heard.first.mono, heard.second.mono, rate_hz=heard.rate_hz, canonicalizer=canonicalizer
        )
        for compared in routes:
            started = time.perf_counter()
            run = _run_route(heard, compared=compared, weights=weights, pitched=pitched, canonicalizer=canonicalizer)
            _write_path(pair_directory / compared.folder, run=run, heard=heard, weights=weights)
            runs.append(run.table)
            _logger.info("%s through %s in %.1f s.", pair.name, compared.folder, time.perf_counter() - started)
        _write_tables(output_directory, runs=tuple(runs))
    return ComparisonSummary(pair_count=len(heard_pairs), route_count=len(routes), output_directory=output_directory)


@dataclass(frozen=True)
class _RenderedRun:
    points: tuple[PathPoint, ...]
    table: RouteOnPair


def _run_route(
    heard: HeardPair,
    *,
    compared: ComparedRoute,
    weights: ComparisonWeights,
    pitched: bool,
    canonicalizer: Canonicalizer,
) -> _RenderedRun:
    started = time.perf_counter()
    prepared = pair_through(compared.named.route, heard.first, heard.second)
    prepare_seconds = time.perf_counter() - started
    points, render_seconds = _render_points(prepared, weights=weights.path)
    path = HeardPath(points=points, first=heard.first.mono, second=heard.second.mono, rate_hz=heard.rate_hz)
    references = tuple(
        PathPoint(
            weight=reference.weight,
            waveform=pair_through(compared.named.route, reference.heard, reference.heard).render(
                weight=FIRST_END_WEIGHT
            ),
        )
        for reference in heard.references
    )
    return _RenderedRun(
        points=points,
        table=RouteOnPair(
            pair=heard.pair,
            folder=compared.folder,
            frame_counts=tuple(int(point.waveform.shape[0]) for point in points),
            timings=RenderTimings(prepare_seconds=prepare_seconds, render_seconds=render_seconds),
            readings=read_path(path),
            pitch=_pitch_path(points, rate_hz=heard.rate_hz, canonicalizer=canonicalizer) if pitched else None,
            transposition_distances_db=transposition_distances_db(points[1:-1], references) if references else (),
        ),
    )


def _write_tables(output_directory: Path, *, runs: tuple[RouteOnPair, ...]) -> None:
    write_table(output_directory / READINGS_FILE_NAME, [row for run in runs for row in point_rows(run)])
    write_table(output_directory / PATHS_FILE_NAME, [path_row(run) for run in runs])
    write_table(output_directory / VERDICTS_FILE_NAME, verdict_rows(runs))


def _render_points(
    prepared: PreparedPair, *, weights: tuple[float, ...]
) -> tuple[tuple[PathPoint, ...], tuple[float, ...]]:
    points = []
    seconds = []
    for weight in weights:
        started = time.perf_counter()
        points.append(PathPoint(weight=weight, waveform=prepared.render(weight=weight)))
        seconds.append(time.perf_counter() - started)
    return tuple(points), tuple(seconds)


def _pitch_path(points: tuple[PathPoint, ...], *, rate_hz: float, canonicalizer: Canonicalizer) -> PitchPath:
    return PitchPath(
        weights=tuple(point.weight for point in points),
        semitones=tuple(heard_pitch(point.waveform, rate_hz=rate_hz, canonicalizer=canonicalizer) for point in points),
    )


def _write_path(directory: Path, *, run: _RenderedRun, heard: HeardPair, weights: ComparisonWeights) -> None:
    """Both ends and every listening weight as files of their own, and the whole path joined into one."""
    for point in run.points:
        if point.weight in weights.written:
            write_rendering(
                RenderedFile(
                    path=directory / f"morph_{int(round(point.weight * PERCENT)):03d}.wav",
                    kind=RenderKind.MORPH if 0.0 < point.weight < 1.0 else RenderKind.RECONSTRUCTION,
                    rate_hz=heard.rate_hz,
                    weight=point.weight,
                ),
                point.waveform,
            )
    write_rendering(
        RenderedFile(path=directory / PATH_FILE_NAME, kind=RenderKind.MORPH, rate_hz=heard.rate_hz, weight=None),
        _joined(tuple(point.waveform for point in run.points), gap_frames=int(PATH_GAP_SECONDS * heard.rate_hz)),
    )


def _joined(waveforms: tuple[NDArray[np.float64], ...], *, gap_frames: int) -> NDArray[np.float64]:
    gap = np.zeros(gap_frames)
    pieces = [piece for waveform in waveforms for piece in (waveform, gap)]
    return np.concatenate(pieces[:-1])


def _write_original(path: Path, sound: OriginalSound, *, weight: float) -> None:
    write_rendering(RenderedFile(path=path, kind=RenderKind.ORIGINAL, rate_hz=sound.rate_hz, weight=weight), sound.mono)


def _manifest(
    pair_set: PairSet, *, routes: tuple[ComparedRoute, ...], weights: ComparisonWeights
) -> dict[str, JsonValue]:
    return {
        "render_revision": RENDER_REVISION,
        "routes": {
            compared.folder: {
                "kind": compared.named.kind.value,
                "name": compared.named.name,
                "device": compared.named.device,
                **compared.named.description,
            }
            for compared in routes
        },
        "path_weights": list(weights.path),
        "listening_weights": list(weights.listening),
        "pair_set": {
            "seed": pair_set.seed,
            "experiment_id": pair_set.experiment_id,
            "digest": pair_set_digest(pair_set),
            "pairs": [pair.name for pair in pair_set.pairs],
        },
    }
