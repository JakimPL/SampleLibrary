from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import ending_in_one_line, non_negative_integer, positive_integer
from samplecore.config import LibraryConfig
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.coordinates.readers import CLASSICAL_READERS, PYIN_READER_NAME, SUBHARMONIC_READER_NAME
from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.measurement.pitch.changes import PitchKeepingMorph, default_changes
from samplemorph.measurement.pitch.reader import PitchReader
from samplemorph.measurement.pitch.reading import DrawnSample, HeldOutReader, SyntheticReader, variants_of
from samplemorph.measurement.pitch.session import PitchReadings, SyntheticSet, write_pitch_readings
from samplemorph.measurement.pitch.synthetic import draw_family_tones, draw_noise_bursts, draw_tone_pairs
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.named import NamedRoute, envelope_route
from samplemorph.routes.route import HeardMono
from samplemorph.training.frame_cache import (
    DEFAULT_FRAME_CACHE_NAME,
    FrameCache,
    frame_cache_directory,
    open_frame_cache,
)
from samplemorph.training.processes import mapped_in_processes
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED
from samplemorph.training.splits import DEFAULT_VALIDATION_SHARE, catalog_classes, split_by_class

COMMAND_NAME: Final[str] = "read-pitch"
DEFAULT_HELD_OUT_COUNT: Final[int] = 200
DEFAULT_TONES_PER_FAMILY: Final[int] = 12
DEFAULT_PAIR_COUNT: Final[int] = 48
DEFAULT_NOISE_COUNT: Final[int] = 24
CLASSICAL_READER_NAMES: Final[tuple[str, ...]] = tuple(CLASSICAL_READERS)
REFEREES: Final[tuple[str, str]] = (SUBHARMONIC_READER_NAME, PYIN_READER_NAME)
MIDDLE_WEIGHT: Final[float] = 0.5
DEFAULT_HEAD_DEVICE: Final[str] = "cpu"
WORKER_CHUNK_SIZE: Final[int] = 1

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnvelopeMiddle:
    """The middle of the envelope route that keeps the first sound's excitation, whose pitch content is the first sound's."""

    route: NamedRoute

    @property
    def name(self) -> str:
        return f"{self.route.name}-middle"

    def middle(self, first: PreparedMono, second: PreparedMono) -> PreparedMono:
        pair = pair_through(
            self.route.route,
            HeardMono(mono=first, rate_hz=NOMINAL_WAV_RATE),
            HeardMono(mono=second, rate_hz=NOMINAL_WAV_RATE),
        )
        return prepare_mono(pair.render(weight=MIDDLE_WEIGHT))


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Read how well pitch readers follow true retunings, known tones and pitch-keeping changes.",
    )
    parser.add_argument(
        "--cache",
        type=str,
        default=DEFAULT_FRAME_CACHE_NAME,
        help="The frame cache whose held-out samples are read, split the way a pitch head is taught on it.",
    )
    parser.add_argument(
        "--readers",
        type=str,
        nargs="+",
        default=CLASSICAL_READER_NAMES,
        help=(
            f"Which readers to read with: {', '.join(CLASSICAL_READER_NAMES)}, or the name a pitch head is stored "
            "under. Both classical readers together also settle where held-out samples lie."
        ),
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_HEAD_DEVICE, help="Which device a stored pitch head reads on."
    )
    parser.add_argument(
        "--samples",
        type=positive_integer,
        default=DEFAULT_HELD_OUT_COUNT,
        help="How many held-out samples to read, each retuned and changed.",
    )
    parser.add_argument(
        "--tones",
        type=non_negative_integer,
        default=DEFAULT_TONES_PER_FAMILY,
        help="How many synthetic tones each family draws.",
    )
    parser.add_argument(
        "--pairs",
        type=non_negative_integer,
        default=DEFAULT_PAIR_COUNT,
        help="How many pairs of tones of different families to read the interval of.",
    )
    parser.add_argument(
        "--noises",
        type=non_negative_integer,
        default=DEFAULT_NOISE_COUNT,
        help="How many noise bursts to read, which a reader's reliability should rank under the tones.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed of the split and every draw.")
    parser.add_argument(
        "--workers",
        type=non_negative_integer,
        default=0,
        help="How many processes read; none reads in this one.",
    )
    parser.add_argument(
        "--output", type=str, required=True, help="The directory to write the tables and pictures into."
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Read held-out samples and synthetic sounds with every reader asked for, and write how each fared.

    The held-out samples are those a pitch head taught on the cache under the same seed is judged
    on, each read as stored, at every true retuning, under every pitch-keeping change, and in the
    middle of the envelope route toward the next sample drawn. The synthetic tones are drawn by
    family, pairs of them across families, and noise bursts stand for sounds with no pitch.

    Raises:
        SystemExit: the cache is not built, or its held-out samples cannot be read now.
    """
    with ending_in_one_line("Read no pitch", (ValueError,)):
        cache = _opened_cache(config.library_root, name=arguments.cache)
        audio = SampleAudio.from_catalog(connection, config.library_root)
        drawn = _drawn_samples(
            _held_out_hashes(connection, cache=cache, random_seed=arguments.seed),
            audio=audio,
            count=arguments.samples,
            random_seed=arguments.seed,
        )
        readers = _readers(
            tuple(dict.fromkeys(arguments.readers)), library_root=config.library_root, device=arguments.device
        )
        reader_names = tuple(reader.name for reader in readers)
        changes = default_changes()
        morphs: tuple[PitchKeepingMorph, ...] = (
            EnvelopeMiddle(route=envelope_route(EnvelopeSettings(excitation=Excitation.FIRST))),
        )
        held_out = tuple(
            mapped_in_processes(
                HeldOutReader(audio=audio, readers=readers, changes=changes, morphs=morphs),
                drawn,
                worker_count=arguments.workers,
                chunk_size=WORKER_CHUNK_SIZE,
                description="Reading held-out samples",
            )
        )
        synthetic = SyntheticSet(
            tones=draw_family_tones(count=arguments.tones, random_seed=arguments.seed),
            pairs=draw_tone_pairs(count=arguments.pairs, random_seed=arguments.seed),
            noises=draw_noise_bursts(count=arguments.noises, random_seed=arguments.seed),
        )
        synthetic_readings = {
            readings.name: readings
            for readings in mapped_in_processes(
                SyntheticReader(readers=readers),
                synthetic.sounds,
                worker_count=arguments.workers,
                chunk_size=WORKER_CHUNK_SIZE,
                description="Reading synthetic sounds",
            )
        }
        summary = write_pitch_readings(
            PitchReadings(
                reader_names=reader_names,
                held_out=held_out,
                synthetic=synthetic,
                synthetic_readings=synthetic_readings,
            ),
            variants=variants_of(changes, morphs),
            referees=REFEREES,
            output_directory=Path(arguments.output),
        )
    _logger.info(
        "Read %d held-out samples and %d synthetic sounds through %s: %d trials, written into %s.",
        len(held_out),
        len(synthetic.sounds),
        ", ".join(reader_names),
        summary.trial_count,
        summary.output_directory,
    )


def _opened_cache(library_root: Path, *, name: str) -> FrameCache:
    """The named frame cache, opened.

    Raises:
        ValueError: no frame cache is built under that name.
    """
    try:
        return open_frame_cache(frame_cache_directory(library_root, name=name))
    except FileNotFoundError as error:
        raise ValueError(f"{error}; build it with cache-frames") from error


def _held_out_hashes(connection: Connection, *, cache: FrameCache, random_seed: int) -> tuple[str, ...]:
    """The cached samples a pitch head taught on this cache under the seed is judged on, in the cache's order."""
    split = split_by_class(
        cache.hashes, classes=catalog_classes(connection), share=DEFAULT_VALIDATION_SHARE, random_seed=random_seed
    )
    return tuple(cache.hashes[int(position)] for position in split.validation_positions)


def _drawn_samples(
    candidates: tuple[str, ...], *, audio: SampleAudio, count: int, random_seed: int
) -> tuple[DrawnSample, ...]:
    """The first `count` candidates in the seed's order that can be read now, each paired with the next one drawn.

    Raises:
        ValueError: no candidate can be read now.
    """
    order = np.random.default_rng(random_seed).permutation(len(candidates))
    readable = [candidates[int(position)] for position in order if audio.is_available(candidates[int(position)])]
    chosen = readable[:count]
    if not chosen:
        raise ValueError("no held-out sample of the cache can be read now")
    return tuple(
        DrawnSample(sample_hash=sample_hash, partner_hash=chosen[(index + 1) % len(chosen)])
        for index, sample_hash in enumerate(chosen)
    )


def _readers(names: tuple[str, ...], *, library_root: Path, device: str) -> tuple[PitchReader, ...]:
    """The readers the names ask for, in the order asked: the classical ones by name, and any other name a stored head.

    The head's weights are imported here, so a command that reads with the classical readers alone
    parses and runs with no network library loaded.

    Raises:
        ValueError: a name is neither a classical reader nor a pitch head stored under it.
    """
    # pylint: disable=import-outside-toplevel
    import torch

    from samplemorph.coordinates.pitch_head.store import load_pitch_head
    from samplemorph.model_paths import pitch_head_path

    readers: list[PitchReader] = []
    for name in names:
        if name in CLASSICAL_READERS:
            readers.append(CLASSICAL_READERS[name]())
            continue
        try:
            readers.append(load_pitch_head(pitch_head_path(library_root, name=name), device=torch.device(device)))
        except FileNotFoundError as error:
            raise ValueError(
                f"{name} is neither a classical reader ({', '.join(CLASSICAL_READER_NAMES)}) nor a stored pitch head; "
                f"{error}"
            ) from error
    return tuple(readers)
