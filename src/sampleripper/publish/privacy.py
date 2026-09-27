from __future__ import annotations

from pathlib import Path
from typing import Final

from sqlalchemy import JSON, Column, Connection, String, cast, exists, func, or_, select

from samplecore.config import LibraryConfig
from samplecore.storage.curation import curation_metadata
from sampleripper.publish.messages import CURATION_REACHED, PRIVATE_VALUE
from sampleripper.publish.rules import catalog_tables

FILESYSTEM_ROOT: Final[str] = "/"


def private_prefixes(config: LibraryConfig) -> tuple[str, ...]:
    """The paths on this computer no published value may name: the library, its collections and the home folder."""
    paths = [config.library_root, *config.sample_directories, Path.home()]
    if config.module_source_directory is not None:
        paths.append(config.module_source_directory)
    return tuple(sorted({path.as_posix() for path in paths} - {FILESYSTEM_ROOT, ""}))


def publication_problems(connection: Connection, *, prefixes: tuple[str, ...]) -> tuple[str, ...]:
    """Everything the publication written on ``connection`` would carry that stays home, one sentence each.

    Every curation table is empty, a person's decisions staying on their computer, and no text of
    any published table names a path of ``prefixes``, which is how a folder of this computer would
    reach a site through a column no rule rewrote.
    """
    curated = tuple(
        CURATION_REACHED.format(table=table.fullname)
        for table in curation_metadata.sorted_tables
        if connection.execute(select(exists().select_from(table))).scalar_one()
    )
    named = tuple(
        PRIVATE_VALUE.format(table=table.fullname, column=column.name)
        for table in catalog_tables()
        for column in table.columns
        if isinstance(column.type, (String, JSON)) and _names_any(connection, column, prefixes)
    )
    return (*curated, *named)


def _names_any(connection: Connection, column: Column[object], prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return False
    matches = or_(*(func.strpos(cast(column, String), prefix) > 0 for prefix in prefixes))
    return bool(connection.execute(select(exists().select_from(column.table).where(matches))).scalar_one())
