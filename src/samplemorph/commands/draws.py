from __future__ import annotations

import argparse
from collections.abc import Collection

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import DEFAULT_ANCHOR, Anchor
from samplemorph.measurement.corpus import DEFAULT_PROBE_FRAME_CEILING, DEFAULT_PROBE_FRAME_FLOOR
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME


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


def require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        ValueError: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise ValueError(f"the catalog holds no sample {sample_hash}")

    return sample
