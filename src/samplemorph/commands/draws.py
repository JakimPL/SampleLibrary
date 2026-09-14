from __future__ import annotations

import argparse
import logging
from collections.abc import Collection

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor
from samplemorph.measurement.corpus import DEFAULT_PROBE_FRAME_CEILING, DEFAULT_PROBE_FRAME_FLOOR
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME

_logger = logging.getLogger(__name__)


def add_canonicalizer_argument(parser: argparse.ArgumentParser, *, help_text: str, names: Collection[str]) -> None:
    """The axis flags every command that canonicalizes shares, declared once so each reads the same.

    `names` are the registered axes the command accepts: every one for a command that analyzes,
    the renderable ones for a command that fits what is later heard.
    """
    parser.add_argument("--canonicalizer", choices=sorted(names), default=DEFAULT_CANONICALIZER_NAME, help=help_text)
    parser.add_argument(
        "--anchor",
        type=Anchor,
        choices=tuple(Anchor),
        default=DEFAULT_ANCHOR,
        help="Which band alignment moves to the reference band: none, the loudest, or the fundamental.",
    )


def canonicalizer_from(arguments: argparse.Namespace) -> Canonicalizer:
    """The canonicalizer the shared axis flags name."""
    return CANONICALIZER_REGISTRY[arguments.canonicalizer](anchor=arguments.anchor)


def draw_probe_samples(connection: Connection, *, count: int, random_seed: int) -> tuple[Sample, ...]:
    """The seeded draw of samples within the probe frame bounds that a fit or a training run reads."""
    return PostgresSampleRepository(connection).sample_reproducibly(
        count=count,
        random_seed=random_seed,
        frame_floor=DEFAULT_PROBE_FRAME_FLOOR,
        frame_ceiling=DEFAULT_PROBE_FRAME_CEILING,
    )


def readable_samples(samples: tuple[Sample, ...], audio: SampleAudio) -> tuple[Sample, ...]:
    """The samples whose audio can be read now, in the order given, naming how many were left out.

    A sample found in a sample directory is read from its file, which can be gone; a fit, a cache or
    a training run sized to its samples holds only the ones it can read.
    """
    readable = tuple(sample for sample in samples if audio.is_available(sample.hash))
    if len(readable) < len(samples):
        _logger.warning("%d sample(s) have no file to read now and are left out.", len(samples) - len(readable))
    return readable


class SampleNotCataloged(ValueError):
    """Raised when a command names a sample hash the catalog holds no sample under."""


def require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        SampleNotCataloged: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise SampleNotCataloged(f"the catalog holds no sample {sample_hash}")

    return sample
