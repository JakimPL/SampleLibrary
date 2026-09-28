from __future__ import annotations

from collections import Counter
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, func, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.module_link import ModuleLink
from samplecore.storage.database import HASH_CHUNK_SIZE, POSTGRES_PARAMETER_LIMIT, chunks, module_link

LINK_ROWS_PER_STATEMENT: Final[int] = POSTGRES_PARAMETER_LIMIT // len(module_link.c)


class ModuleLinkRepository(Protocol):
    """Persistence for the page each module came from: at most one link per cataloged module."""

    def upsert_many(self, links: tuple[ModuleLink, ...]) -> None: ...

    def get_many(self, hashes: list[str]) -> dict[str, ModuleLink]: ...

    def list_all(self) -> tuple[ModuleLink, ...]: ...

    def count(self) -> int: ...


class PostgresModuleLinkRepository:
    """A ModuleLinkRepository backed by the catalog's ``module_link`` table."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert_many(self, links: tuple[ModuleLink, ...]) -> None:
        """Write each link over whatever its module held, in statements Postgres binds.

        Raises:
            ValueError: two links name one module, which leaves no one page for its row to name.
        """
        repeated = sorted(
            module_hash
            for module_hash, occurrences in Counter(link.module_hash for link in links).items()
            if occurrences > 1
        )
        if repeated:
            raise ValueError(f"one write names these modules more than once: {', '.join(repeated)}")

        for batch in chunks(links, LINK_ROWS_PER_STATEMENT):
            statement = insert(module_link).values(
                [{"module_hash": link.module_hash, "url": link.url} for link in batch]
            )
            statement = statement.on_conflict_do_update(
                index_elements=[module_link.c.module_hash], set_={"url": statement.excluded.url}
            )
            self._connection.execute(statement)

    def get_many(self, hashes: list[str]) -> dict[str, ModuleLink]:
        """The link held for each of ``hashes`` that carries one, read in chunks Postgres binds."""
        links: dict[str, ModuleLink] = {}
        for chunk in chunks(hashes, HASH_CHUNK_SIZE):
            statement = select(module_link).where(module_link.c.module_hash.in_(chunk))
            links.update({row.module_hash: _row_to_module_link(row) for row in self._connection.execute(statement)})
        return links

    def list_all(self) -> tuple[ModuleLink, ...]:
        rows = self._connection.execute(select(module_link).order_by(module_link.c.module_hash)).fetchall()
        return tuple(_row_to_module_link(row) for row in rows)

    def count(self) -> int:
        # func.count() is SQLAlchemy's dynamically-generated SQL COUNT(*), invisible to pylint's static analysis.
        # pylint: disable-next=not-callable
        return self._connection.execute(select(func.count()).select_from(module_link)).scalar_one()


def _row_to_module_link(row: Row[Any]) -> ModuleLink:
    """Reconstruct a ModuleLink from a Core row, addressed by its own column names."""
    return ModuleLink(module_hash=row.module_hash, url=row.url)
