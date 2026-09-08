from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from samplecore.sharding import WHOLE, Shard, parse_shard

WORK_LIST = tuple(range(10))


@dataclass(frozen=True)
class SplitCase:
    """One way of splitting a work list, and what the shares should hold."""

    count: int
    shares: tuple[tuple[int, ...], ...]


@pytest.mark.parametrize(
    "case",
    [
        SplitCase(count=1, shares=(WORK_LIST,)),
        SplitCase(count=2, shares=((0, 2, 4, 6, 8), (1, 3, 5, 7, 9))),
        SplitCase(count=3, shares=((0, 3, 6, 9), (1, 4, 7), (2, 5, 8))),
    ],
)
def test_the_shares_of_a_split_cover_the_work_list_exactly_once(case: SplitCase) -> None:
    shares = tuple(Shard(index=index, count=case.count).select(WORK_LIST) for index in range(case.count))

    assert shares == case.shares
    assert sorted(item for share in shares for item in share) == list(WORK_LIST)


def test_a_split_finer_than_the_work_list_leaves_the_last_shares_empty() -> None:
    """More runs than items is wasteful rather than wrong, so the extra runs simply find nothing."""
    shares = tuple(Shard(index=index, count=4).select((1, 2)) for index in range(4))

    assert shares == ((1,), (2,), (), ())


def test_a_share_is_taken_by_striding_so_every_run_sees_a_like_mixture() -> None:
    """A work list ordered by path groups similar files, which contiguous blocks would hand unevenly."""
    ordered_by_size = tuple(range(100))

    first_share = Shard(index=0, count=2).select(ordered_by_size)

    assert min(first_share) == 0
    assert max(first_share) == 98


def test_the_whole_work_list_is_the_share_of_a_run_that_is_the_only_one() -> None:
    assert WHOLE.select(WORK_LIST) == WORK_LIST
    assert WHOLE.is_whole


def test_a_share_of_a_split_knows_it_is_not_the_whole() -> None:
    assert not Shard(index=0, count=2).is_whole


@pytest.mark.parametrize(
    ("index", "count"),
    [(2, 2), (5, 2), (-1, 2), (0, 0), (0, -1)],
)
def test_a_shard_naming_no_real_share_is_rejected(index: int, count: int) -> None:
    with pytest.raises(ValidationError):
        Shard(index=index, count=count)


def test_a_shard_reads_back_from_the_text_it_prints() -> None:
    shard = Shard(index=2, count=5)

    assert parse_shard(str(shard)) == shard


@pytest.mark.parametrize("text", ["", "3", "x/2", "1/y", "1/2/3", "/", "1/"])
def test_text_that_is_not_an_index_over_a_count_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_shard(text)
