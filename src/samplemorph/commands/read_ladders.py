from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import ending_in_one_line, non_negative_integer, positive_integer
from samplecore.config import LibraryConfig
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.measurement.ladders import walkers as ladder_walkers
from samplemorph.measurement.ladders.axis import PooledAxis
from samplemorph.measurement.ladders.session import read_ladders
from samplemorph.measurement.ladders.truth import (
    SYNTHETIC_FAMILIES,
    Ladder,
    LadderRecipe,
    UnrelatedPair,
    draw_synthetic_ends,
    ladder_weights,
    retuned_ladder,
    synthetic_ladder,
)
from samplemorph.measurement.ladders.walkers import CrossfadeWalker, LadderWalker, TranslationOracle
from samplemorph.registries import canonicalizer_for_geometry
from samplemorph.training.descriptor_cache import (
    DEFAULT_GRID_CACHE_NAME,
    GridCache,
    grid_cache_directory,
    open_grid_cache,
)
from samplemorph.training.processes import mapped_in_processes
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED

COMMAND_NAME: Final[str] = "read-ladders"
DEFAULT_LADDER_SAMPLE_COUNT: Final[int] = 100
DEFAULT_SYNTHETIC_COUNT: Final[int] = 12
DEFAULT_UNRELATED_COUNT: Final[int] = 24
DEFAULT_INTERVALS_SEMITONES: Final[tuple[float, ...]] = (3.0, 5.0, 7.0, 12.0)
DEFAULT_STEP_COUNT: Final[int] = 9
DEFAULT_MINIMUM_SECONDS: Final[float] = 0.5
DEFAULT_WALKER_NAMES: Final[tuple[str, ...]] = (
    ladder_walkers.CROSSFADE_WALKER_NAME,
    ladder_walkers.ORACLE_WALKER_NAME,
)
HASH_PREFIX_LENGTH: Final[int] = 12
WORKER_CHUNK_SIZE: Final[int] = 2

_logger = logging.getLogger(__name__)


class UnknownWalker(ValueError):
    """Raised when the command names a model to read ladders through that it has none of."""


@dataclass(frozen=True)
class _Drawn:
    """One library sample read into its ladders, beside its stored reading for the unrelated pairs."""

    sample_hash: str
    stored: NDArray[np.float32]
    ladders: tuple[Ladder, ...]


@dataclass(frozen=True)
class _LadderMaker:
    """Reads one sample and builds its ladders; built once and sent to every worker process."""

    audio: SampleAudio
    axis: PooledAxis
    intervals: tuple[float, ...]
    weights: tuple[float, ...]

    def __call__(self, sample_hash: str) -> _Drawn:
        recipe = LadderRecipe(canonicalizer=canonicalizer_for_geometry(self.axis.geometry), axis=self.axis)
        mono = prepare_mono(self.audio.read_by_hash(sample_hash).pcm)
        return _Drawn(
            sample_hash=sample_hash,
            stored=recipe.pooled(recipe.canonicalizer.canonicalize(mono)),
            ladders=tuple(
                retuned_ladder(
                    mono,
                    name=f"{sample_hash[:HASH_PREFIX_LENGTH]}-{interval:g}st",
                    interval_semitones=interval,
                    weights=self.weights,
                    recipe=recipe,
                )
                for interval in self.intervals
            ),
        )


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Read how far paths between two grids move rather than fade, on ladders whose middle is known.",
    )
    parser.add_argument(
        "--cache",
        type=str,
        default=DEFAULT_GRID_CACHE_NAME,
        help="The grid cache whose axis and pooling every ladder is made on, and whose samples it draws.",
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=DEFAULT_WALKER_NAMES,
        help=f"Which paths to read: {', '.join(DEFAULT_WALKER_NAMES)}.",
    )
    parser.add_argument(
        "--samples",
        type=positive_integer,
        default=DEFAULT_LADDER_SAMPLE_COUNT,
        help="How many library samples to retune into ladders.",
    )
    parser.add_argument(
        "--synthetic",
        type=non_negative_integer,
        default=DEFAULT_SYNTHETIC_COUNT,
        help="How many synthetic ladders each synthetic family draws.",
    )
    parser.add_argument(
        "--unrelated",
        type=non_negative_integer,
        default=DEFAULT_UNRELATED_COUNT,
        help="How many pairs of unrelated library samples to read paths between.",
    )
    parser.add_argument(
        "--intervals",
        type=float,
        nargs="+",
        default=DEFAULT_INTERVALS_SEMITONES,
        help="The intervals, in semitones, a ladder moves over.",
    )
    parser.add_argument(
        "--steps", type=positive_integer, default=DEFAULT_STEP_COUNT, help="How many steps a ladder has, ends included."
    )
    parser.add_argument(
        "--minimum-seconds",
        type=float,
        default=DEFAULT_MINIMUM_SECONDS,
        help="How long a sample must last at the highest step of its widest ladder.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed of every draw.")
    parser.add_argument(
        "--workers",
        type=non_negative_integer,
        default=0,
        help="How many processes build the ladders; none builds them in this one.",
    )
    parser.add_argument(
        "--output", type=str, required=True, help="The directory to write the tables and pictures into."
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Build ladders with a known middle, walk each through every named path, and write what the paths do.

    Library samples are drawn from the cache by the seed, each read at rates spanning every
    interval; synthetic tones move their pitch, their resonance or both the opposite way; and
    unrelated pairs of the drawn samples show how a path runs where nobody knows the middle.

    Raises:
        SystemExit: the cache is not built, a model name is unknown, the steps or intervals leave
            nothing to read, or every ladder stands too close to its own crossfade.
    """
    with ending_in_one_line("Read no ladder", (ValueError,)):
        cache = _opened_cache(config.library_root, name=arguments.cache)
        axis = PooledAxis(
            geometry=cache.description.geometry,
            band_count=cache.description.band_count,
            bands_per_semitone=cache.description.bands_per_semitone,
        )
        walkers = _walkers(tuple(dict.fromkeys(arguments.models)), axis=axis)
        weights = ladder_weights(arguments.steps)
        intervals = _intervals(arguments.intervals)
        audio = SampleAudio.from_catalog(connection, config.library_root)
        sample_hashes = _drawn_hashes(
            cache,
            audio=audio,
            count=arguments.samples,
            minimum_frames=_minimum_frames(arguments.minimum_seconds, axis=axis, widest=max(intervals)),
            random_seed=arguments.seed,
        )
        drawn = tuple(
            mapped_in_processes(
                _LadderMaker(audio=audio, axis=axis, intervals=intervals, weights=weights),
                sample_hashes,
                worker_count=arguments.workers,
                chunk_size=WORKER_CHUNK_SIZE,
                description="Building ladders",
            )
        )
        recipe = LadderRecipe(canonicalizer=canonicalizer_for_geometry(axis.geometry), axis=axis)
        ladders = (
            *(ladder for sample in drawn for ladder in sample.ladders),
            *_synthetic_ladders(
                count=arguments.synthetic, intervals=intervals, weights=weights, recipe=recipe, seed=arguments.seed
            ),
        )
        summary = read_ladders(
            ladders,
            _unrelated_pairs(drawn, count=arguments.unrelated, weights=weights),
            walkers=walkers,
            axis=axis,
            output_directory=Path(arguments.output),
        )
    _logger.info(
        "Read %d ladders and %d unrelated pairs through %s into %s; %d stood too close to their crossfade to read.",
        summary.ladder_count,
        summary.pair_count,
        ", ".join(walker.name for walker in walkers),
        summary.output_directory,
        summary.skipped_count,
    )


def _opened_cache(library_root: Path, *, name: str) -> GridCache:
    """The named cache, opened.

    Raises:
        ValueError: no cache is built under that name.
    """
    try:
        return open_grid_cache(grid_cache_directory(library_root, name=name))
    except FileNotFoundError as error:
        raise ValueError(f"{error}; build it with cache-grids") from error


def _walkers(names: tuple[str, ...], *, axis: PooledAxis) -> tuple[LadderWalker, ...]:
    """The paths the names ask for.

    Raises:
        UnknownWalker: a name is none of the paths this command reads.
    """
    walkers: list[LadderWalker] = []
    for name in names:
        match name:
            case ladder_walkers.CROSSFADE_WALKER_NAME:
                walkers.append(CrossfadeWalker())
            case ladder_walkers.ORACLE_WALKER_NAME:
                walkers.append(TranslationOracle(bands_per_semitone=axis.bands_per_semitone))
            case _:
                raise UnknownWalker(f"no path is named {name}; the paths are {', '.join(DEFAULT_WALKER_NAMES)}")
    return tuple(walkers)


def _intervals(requested: list[float]) -> tuple[float, ...]:
    """The distinct intervals asked for, in the order given.

    Raises:
        ValueError: an interval is not a positive number of semitones.
    """
    if any(interval <= 0.0 for interval in requested):
        raise ValueError("every interval must be a positive number of semitones")
    return tuple(dict.fromkeys(requested))


def _minimum_frames(minimum_seconds: float, *, axis: PooledAxis, widest: float) -> int:
    """The frames a stored sample needs to last `minimum_seconds` at the top of the widest ladder, retuned half its width up."""
    shortening = 2.0 ** (widest / 2.0 / SEMITONES_PER_OCTAVE)
    return int(np.ceil(minimum_seconds * axis.geometry.analysis_rate_hz * shortening))


def _drawn_hashes(
    cache: GridCache, *, audio: SampleAudio, count: int, minimum_frames: int, random_seed: int
) -> tuple[str, ...]:
    """The first `count` of the cache's samples, in the seed's order, that can be read now and last long enough.

    Raises:
        ValueError: no cached sample can be read and lasts long enough.
    """
    chosen: list[str] = []
    for position in np.random.default_rng(random_seed).permutation(cache.sample_count):
        sample_hash = cache.hashes[int(position)]
        if audio.is_available(sample_hash) and audio.frame_count(sample_hash) >= minimum_frames:
            chosen.append(sample_hash)
        if len(chosen) == count:
            break
    if not chosen:
        raise ValueError(f"no sample in the cache can be read now and lasts {minimum_frames} frames or more")
    return tuple(chosen)


def _synthetic_ladders(
    *, count: int, intervals: tuple[float, ...], weights: tuple[float, ...], recipe: LadderRecipe, seed: int
) -> tuple[Ladder, ...]:
    return tuple(
        synthetic_ladder(ends, weights=weights, recipe=recipe)
        for family in SYNTHETIC_FAMILIES
        for ends in draw_synthetic_ends(family, count=count, intervals=intervals, random_seed=seed)
    )


def _unrelated_pairs(drawn: tuple[_Drawn, ...], *, count: int, weights: tuple[float, ...]) -> tuple[UnrelatedPair, ...]:
    """Consecutive drawn samples paired off, as many pairs as asked for and the draw holds."""
    return tuple(
        UnrelatedPair(
            name=f"{first.sample_hash[:HASH_PREFIX_LENGTH]}-{second.sample_hash[:HASH_PREFIX_LENGTH]}",
            weights=weights,
            ends=np.stack([first.stored, second.stored]),
        )
        for first, second in list(zip(drawn[0::2], drawn[1::2]))[:count]
    )
