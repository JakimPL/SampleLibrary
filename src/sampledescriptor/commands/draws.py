from __future__ import annotations

import argparse
import logging
from collections.abc import Collection
from typing import Final

from sqlalchemy import Connection

from samplecore.config import DEFAULT_MINIMUM_SAMPLE_FRAMES
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor

# Every sample the catalog holds clears its own ingest floor, and none is too long to read, so a
# draw with these bounds reaches the whole catalog.
CATALOG_FRAME_FLOOR: Final[int] = DEFAULT_MINIMUM_SAMPLE_FRAMES
CATALOG_FRAME_CEILING: Final[int] = 2**31 - 1

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


def draw_cached_samples(
    connection: Connection, audio: SampleAudio, *, count: int | None, random_seed: int
) -> tuple[Sample, ...]:
    """The samples a cache holds: every readable sample of the catalog, or a seeded draw of `count` of them."""
    repository = PostgresSampleRepository(connection)
    return readable_samples(
        (
            repository.list_all()
            if count is None
            else repository.sample_reproducibly(
                count=count,
                random_seed=random_seed,
                frame_floor=CATALOG_FRAME_FLOOR,
                frame_ceiling=CATALOG_FRAME_CEILING,
            )
        ),
        audio,
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
