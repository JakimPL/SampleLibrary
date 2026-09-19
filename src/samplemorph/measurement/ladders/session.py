from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samplecore.tables import TableValue, write_table
from samplemorph.measurement.ladders.axis import PooledAxis
from samplemorph.measurement.ladders.pictures import LadderPanel, LadderPicture, draw_ladder
from samplemorph.measurement.ladders.readings import (
    MINIMUM_DISCRIMINATION_DB,
    pair_endpoint_distance_db,
    read_ladder,
    read_pair,
    truth_discrimination_db,
)
from samplemorph.measurement.ladders.tables import (
    ReadLadder,
    ReadPair,
    ladder_rows,
    ladder_summary_rows,
    pair_rows,
    pair_summary_rows,
)
from samplemorph.measurement.ladders.truth import Ladder, LadderFamily, UnrelatedPair
from samplemorph.measurement.ladders.walkers import LadderWalker

LADDERS_FILE_NAME: Final[str] = "ladders.csv"
SUMMARY_FILE_NAME: Final[str] = "summary.csv"
PAIRS_FILE_NAME: Final[str] = "pairs.csv"
PAIR_SUMMARY_FILE_NAME: Final[str] = "pairs_summary.csv"
PICTURES_DIRECTORY_NAME: Final[str] = "pictures"
TRUTH_PANEL_LABEL: Final[str] = "truth"
PICTURE_SUFFIX: Final[str] = ".png"


@dataclass(frozen=True)
class LadderSummary:
    """What one reading wrote: how many ladders and pairs were read, and how many were too alike at the ends to read."""

    ladder_count: int
    pair_count: int
    skipped_count: int
    output_directory: Path


def read_ladders(
    ladders: tuple[Ladder, ...],
    pairs: tuple[UnrelatedPair, ...],
    *,
    walkers: tuple[LadderWalker, ...],
    axis: PooledAxis,
    output_directory: Path,
) -> LadderSummary:
    """Walk every ladder and pair with every walker, read each path, and write the tables and the pictures.

    A ladder whose middle stands closer to the crossfade of its ends than `MINIMUM_DISCRIMINATION_DB`
    has no move to tell from a crossfade, as a flat noise retuned by a few semitones has none, and
    a pair whose ends stand that close has no path to read; both are left out and counted. Every
    ladder read gets one picture holding its truth and every walker's path, and every pair one
    holding every walker's path. `ladders.csv` and `pairs.csv` hold one row per step,
    `summary.csv` and `pairs_summary.csv` the medians of the central steps.

    Raises:
        ValueError: no ladder and no pair is far enough apart at its ends to read.
    """
    readable_ladders = tuple(
        ladder for ladder in ladders if truth_discrimination_db(ladder, axis=axis) >= MINIMUM_DISCRIMINATION_DB
    )
    readable_pairs = tuple(
        pair for pair in pairs if pair_endpoint_distance_db(pair.ends, axis=axis) >= MINIMUM_DISCRIMINATION_DB
    )
    if not readable_ladders and not readable_pairs:
        raise ValueError("every ladder and pair stands too close to its own crossfade to read")

    ladder_reads = tuple(
        read
        for ladder in readable_ladders
        for read in _walked_ladder(ladder, walkers=walkers, axis=axis, output_directory=output_directory)
    )
    pair_reads = tuple(
        read
        for pair in readable_pairs
        for read in _walked_pair(pair, walkers=walkers, axis=axis, output_directory=output_directory)
    )
    _write_tables(
        output_directory,
        (
            (LADDERS_FILE_NAME, [row for read in ladder_reads for row in ladder_rows(read)]),
            (SUMMARY_FILE_NAME, ladder_summary_rows(ladder_reads)),
            (PAIRS_FILE_NAME, [row for read in pair_reads for row in pair_rows(read)]),
            (PAIR_SUMMARY_FILE_NAME, pair_summary_rows(pair_reads)),
        ),
    )
    return LadderSummary(
        ladder_count=len(readable_ladders),
        pair_count=len(readable_pairs),
        skipped_count=len(ladders) - len(readable_ladders) + len(pairs) - len(readable_pairs),
        output_directory=output_directory,
    )


def _walked_ladder(
    ladder: Ladder, *, walkers: tuple[LadderWalker, ...], axis: PooledAxis, output_directory: Path
) -> list[ReadLadder]:
    reads = []
    panels = [LadderPanel(label=TRUTH_PANEL_LABEL, grids=ladder.truth)]
    for walker in walkers:
        walk = walker.walk(ladder)
        if walk is None:
            continue
        reads.append(ReadLadder(walker=walker.name, ladder=ladder, steps=read_ladder(ladder, walk, axis=axis)))
        panels.append(LadderPanel(label=walker.name, grids=walk.path))
    draw_ladder(
        _picture_path(output_directory, family=ladder.family, name=ladder.name),
        LadderPicture(
            title=f"{ladder.name}, {ladder.interval_semitones:g} semitones",
            panels=tuple(panels),
            weights=ladder.weights,
            reading_bands=axis.reading_bands(interval_semitones=ladder.interval_semitones),
        ),
        axis=axis,
    )
    return reads


def _walked_pair(
    pair: UnrelatedPair, *, walkers: tuple[LadderWalker, ...], axis: PooledAxis, output_directory: Path
) -> list[ReadPair]:
    reads = []
    panels = []
    for walker in walkers:
        walk = walker.walk_pair(pair)
        if walk is None:
            continue
        reads.append(ReadPair(walker=walker.name, pair=pair.name, steps=read_pair(pair, walk, axis=axis)))
        panels.append(LadderPanel(label=walker.name, grids=walk.path))
    if panels:
        draw_ladder(
            _picture_path(output_directory, family=LadderFamily.UNRELATED, name=pair.name),
            LadderPicture(
                title=pair.name,
                panels=tuple(panels),
                weights=pair.weights,
                reading_bands=axis.reading_bands(interval_semitones=0.0),
            ),
            axis=axis,
        )
    return reads


def _picture_path(output_directory: Path, *, family: LadderFamily, name: str) -> Path:
    return output_directory / PICTURES_DIRECTORY_NAME / family.value / f"{name}{PICTURE_SUFFIX}"


def _write_tables(output_directory: Path, tables: tuple[tuple[str, list[dict[str, TableValue]]], ...]) -> None:
    for file_name, rows in tables:
        if rows:
            write_table(output_directory / file_name, rows)
