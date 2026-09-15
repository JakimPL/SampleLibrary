from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PositiveFloat

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, SampleHash


class PairEnd(BaseModel):
    """One sound of a drawn pair: the sample, and the label it was drawn under."""

    model_config = FROZEN

    sample_hash: SampleHash
    label: str


class CatalogPair(BaseModel):
    """Two catalog samples, each heard at the rate the library plays it at."""

    model_config = FROZEN

    kind: Literal["catalog"] = "catalog"
    name: str
    first: PairEnd
    second: PairEnd


class RetunedPair(BaseModel):
    """One catalog sample heard at two rates.

    The sound between the two is the same sample heard at the rate between them, which is what a
    route that moves pitch and length together is held against.
    """

    model_config = FROZEN

    kind: Literal["retuned"] = "retuned"
    name: str
    sample: PairEnd
    first_rate_hz: PositiveFloat
    second_rate_hz: PositiveFloat


DrawnPair = Annotated[CatalogPair | RetunedPair, Field(discriminator="kind")]


class PairSet(BaseModel):
    """The pairs one seeded draw chose, under the scoring whose labels it drew by.

    A comparison reads the pairs from this file, so the same set can be rendered again through
    other routes or settings and the listening verdicts stay attached to the same sounds.
    """

    model_config = FROZEN

    seed: int
    experiment_id: Index
    pairs: tuple[DrawnPair, ...]


def write_pair_set(path: Path, pair_set: PairSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pair_set.model_dump_json(indent=2), encoding="utf-8")


def read_pair_set(path: Path) -> PairSet:
    """The pair set a file holds.

    Raises:
        OSError: the file cannot be read.
        pydantic.ValidationError: the file holds no valid pair set.
    """
    return PairSet.model_validate_json(path.read_text(encoding="utf-8"))


def pair_set_digest(pair_set: PairSet) -> str:
    """A digest naming the pairs a set holds, whatever file they were read from."""
    return hashlib.sha256(pair_set.model_dump_json().encode()).hexdigest()
