from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Final

import numpy as np
import soundfile
from sqlalchemy import Connection

from samplecore.auditory.sound_type import SoundType, sound_type_reading
from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import positive_integer
from samplecore.config import LibraryConfig
from samplecore.models.sample import Sample
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.codecs import SampleCodec
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.commands.draws import (
    SampleNotCataloged,
    add_canonicalizer_argument,
    canonicalizer_from,
    draw_probe_samples,
    require_sample,
)
from samplemorph.commands.vocoders import vocoder_from
from samplemorph.measurement.loudness import match_loudness
from samplemorph.measurement.readings import ReconstructionReadings, read_reconstruction
from samplemorph.model_store import DEFAULT_MODEL_NAME, load_named_model
from samplemorph.pipeline import encode_sample
from samplemorph.registries import RENDERABLE_CANONICALIZER_NAMES, canonicalizer_for_geometry
from samplemorph.route_arguments import add_vocoder_arguments
from samplemorph.training.run_settings import DEFAULT_ACCELERATOR, DEFAULT_RANDOM_SEED
from samplemorph.vocoders import Vocoder

COMMAND_NAME: Final[str] = "measure"
IDENTITY_MODEL_NAME: Final[str] = "identity"
DEFAULT_MEASURE_SAMPLE_COUNT: Final[int] = 40
READINGS_FILE_NAME: Final[str] = "readings.csv"
ORIGINAL_FILE_NAME: Final[str] = "original.wav"
RECONSTRUCTION_FILE_NAME: Final[str] = "reconstruction.wav"
HASH_PREFIX_LENGTH: Final[int] = 12
OVERALL_GROUP: Final[str] = "all"
SUMMARY_QUARTILES: Final[tuple[float, float]] = (25.0, 75.0)

_logger = logging.getLogger(__name__)

TableValue = str | int | float | bool


@dataclass(frozen=True)
class MeasuredRoute:
    """The route every probe takes from the catalog to a written pair, and where the pair lands."""

    model: str
    canonicalizer: Canonicalizer
    codec: SampleCodec
    vocoder: Vocoder
    output_directory: Path


@dataclass(frozen=True)
class ProbeReading:
    """One probe's readings beside what identifies it in the table."""

    sample_hash: str
    sound_type: SoundType
    rate_hz: int
    seconds: float
    model: str
    readings: ReconstructionReadings

    def row(self) -> dict[str, TableValue]:
        return {
            "hash": self.sample_hash,
            "sound_type": self.sound_type.value,
            "rate_hz": self.rate_hz,
            "seconds": round(self.seconds, 3),
            "model": self.model,
            **asdict(self.readings),
        }


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Reconstruct probe samples through a stored model and read what the reconstruction costs.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help=f"Which stored model to reconstruct through, or {IDENTITY_MODEL_NAME} for the representation alone.",
    )
    add_canonicalizer_argument(
        parser,
        help_text=f"The axis the {IDENTITY_MODEL_NAME} model reads; a stored model brings its own.",
        names=RENDERABLE_CANONICALIZER_NAMES,
    )
    add_vocoder_arguments(parser, device_default=DEFAULT_ACCELERATOR)
    parser.add_argument(
        "--samples",
        type=positive_integer,
        default=DEFAULT_MEASURE_SAMPLE_COUNT,
        help="How many probes the seeded draw reads.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed of the draw.")
    parser.add_argument(
        "--hashes", type=str, default=None, help="A file naming one sample hash per line, read in place of the draw."
    )
    parser.add_argument(
        "--output", type=str, required=True, help="The directory to write the audio and the readings into."
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Reconstruct every probe through the model and the vocoder, write the pair, and read it.

    Each probe comes back as `<sound type>_<hash prefix>/original.wav` and `reconstruction.wav`,
    matched in loudness under one headroom, at the rate the sample is heard at; `readings.csv`
    holds one row per probe, and the log the medians per sound type. The probes are resolved
    before any model loads, so a draw or a hashes file naming none ends the process at once.

    Raises:
        SystemExit: no probe was named or drawn, the hashes file cannot be read, or it names a hash
            the catalog holds no sample under.
    """
    try:
        probes = _probes(connection, arguments)
    except (SampleNotCataloged, OSError) as error:
        _logger.error("Measured nothing: %s.", error)
        sys.exit(1)
    if not probes:
        _logger.error("No probe to measure: the draw or the hashes file names no sample.")
        sys.exit(1)
    canonicalizer, codec = _codec_for(config, arguments)
    route = MeasuredRoute(
        model=arguments.model,
        canonicalizer=canonicalizer,
        codec=codec,
        vocoder=vocoder_from(arguments, library_root=config.library_root),
        output_directory=Path(arguments.output),
    )
    readings = tuple(_measure(connection, config.library_root, sample, route=route) for sample in probes)
    _write_table(route.output_directory / READINGS_FILE_NAME, readings)
    _report(readings)
    _logger.info("Wrote %d probes through %s into %s.", len(readings), route.model, route.output_directory)


def _codec_for(config: LibraryConfig, arguments: argparse.Namespace) -> tuple[Canonicalizer, SampleCodec]:
    """The codec the flags name beside the canonicalizer it reads: a stored model's own, or the identity."""
    if arguments.model == IDENTITY_MODEL_NAME:
        canonicalizer = canonicalizer_from(arguments)
        return canonicalizer, IdentityCodec(canonicalizer.geometry)

    model = load_named_model(config.library_root, name=arguments.model, device=arguments.device).model
    return canonicalizer_for_geometry(model.description.geometry), model.codec


def _probes(connection: Connection, arguments: argparse.Namespace) -> tuple[Sample, ...]:
    if arguments.hashes is None:
        return draw_probe_samples(connection, count=arguments.samples, random_seed=arguments.seed)

    named = Path(arguments.hashes).read_text(encoding="utf-8").split()
    return tuple(require_sample(connection, sample_hash) for sample_hash in named)


def _measure(connection: Connection, library_root: Path, sample: Sample, *, route: MeasuredRoute) -> ProbeReading:
    encoded = encode_sample(connection, library_root, sample, canonicalizer=route.canonicalizer, codec=route.codec)
    reconstruction = route.vocoder.synthesize(route.canonicalizer.restore(route.codec.decode(encoded.latent)))
    frames = min(encoded.mono.shape[0], reconstruction.shape[0])
    rate_hz = int(round(encoded.rate_hz))
    sound_type = sound_type_reading(encoded.mono, sample_rate_hz=NOMINAL_WAV_RATE).sound_type
    original, matched = match_loudness(
        (encoded.mono[:frames], reconstruction[:frames]), reference=encoded.mono[:frames], source_rate_hz=rate_hz
    )
    directory = route.output_directory / f"{sound_type.value}_{sample.hash[:HASH_PREFIX_LENGTH]}"
    directory.mkdir(parents=True, exist_ok=True)
    soundfile.write(directory / ORIGINAL_FILE_NAME, original, rate_hz, subtype="PCM_16")
    soundfile.write(directory / RECONSTRUCTION_FILE_NAME, matched, rate_hz, subtype="PCM_16")
    return ProbeReading(
        sample_hash=sample.hash,
        sound_type=sound_type,
        rate_hz=rate_hz,
        seconds=frames / rate_hz,
        model=route.model,
        readings=read_reconstruction(matched, original, source_rate_hz=rate_hz),
    )


def _write_table(path: Path, readings: tuple[ProbeReading, ...]) -> None:
    rows = [reading.row() for reading in readings]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _report(readings: tuple[ProbeReading, ...]) -> None:
    """The median and quartiles of every reading, per sound type and over every probe."""
    groups: dict[str, list[ReconstructionReadings]] = defaultdict(list)
    for reading in readings:
        groups[reading.sound_type.value].append(reading.readings)
        groups[OVERALL_GROUP].append(reading.readings)
    for group, members in groups.items():
        for field in fields(ReconstructionReadings):
            values = np.array([float(getattr(member, field.name)) for member in members])
            lower, upper = np.percentile(values, SUMMARY_QUARTILES)
            _logger.info(
                "%-10s %-20s n=%-3d median %+9.4f  [%+9.4f %+9.4f]",
                group,
                field.name,
                values.size,
                float(np.median(values)),
                float(lower),
                float(upper),
            )
