from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from samplemorph.listening.pairs import (
    CatalogPair,
    PairEnd,
    PairSet,
    RetunedPair,
    pair_set_digest,
    read_pair_set,
    write_pair_set,
)

FIRST_HASH: Final[str] = "a" * 64
SECOND_HASH: Final[str] = "b" * 64


@pytest.fixture
def pair_set() -> PairSet:
    return PairSet(
        seed=3,
        experiment_id=1,
        pairs=(
            CatalogPair(
                name="01-same-piano",
                first=PairEnd(sample_hash=FIRST_HASH, label="PIANO"),
                second=PairEnd(sample_hash=SECOND_HASH, label="PIANO"),
            ),
            RetunedPair(
                name="02-retuned-tonal",
                sample=PairEnd(sample_hash=FIRST_HASH, label="PIANO"),
                first_rate_hz=8363.0,
                second_rate_hz=12544.5,
            ),
        ),
    )


def test_a_pair_set_reads_back_as_written(pair_set: PairSet, tmp_path: Path) -> None:
    path = tmp_path / "pairs.json"

    write_pair_set(path, pair_set)

    assert read_pair_set(path) == pair_set


def test_the_digest_follows_the_pairs(pair_set: PairSet) -> None:
    reordered = pair_set.model_copy(update={"pairs": tuple(reversed(pair_set.pairs))})

    assert pair_set_digest(pair_set) == pair_set_digest(pair_set.model_copy())
    assert pair_set_digest(pair_set) != pair_set_digest(reordered)
