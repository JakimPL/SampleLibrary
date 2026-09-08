from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Self, TypeVar

from pydantic import BaseModel, model_validator

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, ShardCount

ItemT = TypeVar("ItemT")

SHARD_SEPARATOR: Final[str] = "/"


class Shard(BaseModel):
    """One run's share of a work list several runs are splitting between them.

    Splitting by hand is what lets a long pass run on more than one core, or more than one machine,
    against a single catalog: each run takes a share, and between them they cover the list once.
    """

    model_config = FROZEN

    index: Index
    count: ShardCount

    @model_validator(mode="after")
    def _index_names_a_real_share(self) -> Self:
        if self.index >= self.count:
            raise ValueError(f"shard {self.index} is outside a split of {self.count}")

        return self

    @property
    def is_whole(self) -> bool:
        """Whether this share is the entire work list, nothing being split."""
        return self.count == WHOLE.count

    def select(self, items: Sequence[ItemT]) -> tuple[ItemT, ...]:
        """This share of ``items``, taken every ``count`` items starting at ``index``.

        Striding rather than slicing into blocks keeps the shares alike: a work list ordered by
        path puts a directory's worth of similar files together, so contiguous blocks would hand
        one run all the large ones. Every run sees the same ordering, so the shares cover the list
        exactly once between them, whichever order the runs happen to start in.
        """
        return tuple(items[self.index :: self.count])

    def __str__(self) -> str:
        return f"{self.index}{SHARD_SEPARATOR}{self.count}"


WHOLE: Final[Shard] = Shard(index=0, count=1)
"""The share a run takes when it is the only one."""


def parse_shard(value: str) -> Shard:
    """Read a shard written as ``index/count``, the form a command line takes it in.

    Raises:
        ValueError: the text is not two numbers separated by a slash, or names no real share.
    """
    index, separator, count = value.partition(SHARD_SEPARATOR)
    if separator == "":
        raise ValueError(f"a shard reads as index{SHARD_SEPARATOR}count, not {value!r}")

    return Shard(index=int(index), count=int(count))
