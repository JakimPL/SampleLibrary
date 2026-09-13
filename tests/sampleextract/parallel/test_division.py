from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from sampleextract.parallel.division import divide

WORK_LIST = tuple(Path(f"module-{index}.xm") for index in range(10))


@dataclass(frozen=True)
class SplitCase:
    """One division of the shared work list, with the shares it is expected to come out as."""

    workers: int
    shares: tuple[tuple[int, ...], ...]


SPLIT_CASES = (
    SplitCase(workers=1, shares=((0, 1, 2, 3, 4, 5, 6, 7, 8, 9),)),
    SplitCase(workers=2, shares=((0, 2, 4, 6, 8), (1, 3, 5, 7, 9))),
    SplitCase(workers=3, shares=((0, 3, 6, 9), (1, 4, 7), (2, 5, 8))),
)


@pytest.mark.parametrize("case", SPLIT_CASES, ids=lambda case: f"{case.workers}-workers")
def test_the_shares_cover_the_work_list_exactly_once(case: SplitCase) -> None:
    shares = divide(WORK_LIST, workers=case.workers)

    assert shares == tuple(tuple(WORK_LIST[index] for index in share) for share in case.shares)
    assert sorted(path for share in shares for path in share) == sorted(WORK_LIST)


def test_a_division_finer_than_the_work_list_leaves_the_later_shares_empty() -> None:
    """A corpus smaller than the worker count still comes out covered once between them."""
    shares = divide(WORK_LIST[:2], workers=4)

    assert shares == ((WORK_LIST[0],), (WORK_LIST[1],), (), ())


def test_striding_gives_each_share_a_like_mixture_of_the_work_list() -> None:
    """Paths sorted by name group a directory's similar files, so blocks would share out unevenly."""
    ordered_by_size = tuple(Path(f"{index:02d}.xm") for index in range(10))

    first_share = divide(ordered_by_size, workers=2)[0]

    assert first_share == tuple(ordered_by_size[index] for index in (0, 2, 4, 6, 8))
