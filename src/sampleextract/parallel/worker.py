from __future__ import annotations

from queue import Queue
from typing import Protocol, TypeVar

from sqlalchemy import Connection

from samplecore.cli_support import open_catalog_connection
from samplecore.config import LibraryConfig
from sampleextract.progress import ProgressSink, QueueProgress

Item = TypeVar("Item")
Summary = TypeVar("Summary")
Item_contra = TypeVar("Item_contra", contravariant=True)
Summary_co = TypeVar("Summary_co", covariant=True)


class ShareCover(Protocol[Item_contra, Summary_co]):
    """The pass one share of a work list runs, over a catalog connection its own process opened."""

    def __call__(
        self,
        config: LibraryConfig,
        connection: Connection,
        items: tuple[Item_contra, ...],
        /,
        *,
        progress: ProgressSink,
    ) -> Summary_co: ...


def cover_share(
    config: LibraryConfig, items: tuple[Item, ...], counts: Queue[int], cover: ShareCover[Item, Summary]
) -> Summary:
    """Cover one share of a work list in a process of its own, reporting each item as it lands.

    The connection is opened here rather than handed in, since a catalog connection belongs to the
    process using it: every entry point in this project opens its own the same way, and the schema
    claim ``connect`` takes settles which of several starting at once creates a fresh catalog's
    tables.
    """
    with open_catalog_connection(config.catalog_url()) as connection:
        return cover(config, connection, items, progress=QueueProgress(counts))
