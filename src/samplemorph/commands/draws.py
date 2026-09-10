from __future__ import annotations

import argparse

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor
from samplemorph.measurement.corpus import DEFAULT_PROBE_FRAME_CEILING, DEFAULT_PROBE_FRAME_FLOOR
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME


def add_canonicalizer_argument(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    """The axis flags every command that canonicalizes shares, declared once so each reads the same."""
    parser.add_argument(
        "--canonicalizer", choices=sorted(CANONICALIZER_REGISTRY), default=DEFAULT_CANONICALIZER_NAME, help=help_text
    )
    parser.add_argument(
        "--anchor",
        type=Anchor,
        choices=tuple(Anchor),
        default=DEFAULT_ANCHOR,
        help="Which band alignment moves to the reference band: the loudest, or the fundamental.",
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
