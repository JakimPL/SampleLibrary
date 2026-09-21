from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Final

from psycopg.errors import LockNotAvailable
from sqlalchemy import Connection, text
from sqlalchemy.exc import OperationalError

from samplecore.storage.audio_store import OBJECTS_DIRECTORY_NAME
from samplecore.storage.database import (
    experiment_id_sequence,
    metadata,
    module_id_sequence,
    sample_relation_id_sequence,
    start_batch,
)

RESET_LOCK_TIMEOUT_MILLISECONDS: Final[int] = 10_000
RETIRED_SUFFIX: Final[str] = ".retired"
CATALOG_SEQUENCES: Final = (module_id_sequence, sample_relation_id_sequence, experiment_id_sequence)

_logger = logging.getLogger(__name__)


class ResetRefused(ValueError):
    """Raised when another connection holds the catalog's tables for longer than a reset waits."""


def reset_library(
    connection: Connection, library_root: Path, *, lock_timeout_milliseconds: int = RESET_LOCK_TIMEOUT_MILLISECONDS
) -> None:
    """Empty every catalog table (feature vectors and experiments included) and the content store.

    The database and its schema stay in place, ready for a fresh extraction pass to rebuild them
    from nothing. Every table empties in one ``TRUNCATE``, which commits whole or leaves the catalog
    as it was, so a reset stopped at any moment leaves either the catalog it found or an empty one;
    the catalog's sequences restart in the same transaction, so a rebuilt catalog numbers its
    modules, relations and experiments from one again. The content
    store empties only once the catalog has, since a store emptied under a catalog still naming its
    objects would be a damaged library. Its ``objects`` directory moves aside and a fresh one takes
    its place before the old one is deleted, so a reset repeated after a stop deletes whatever an
    earlier one left aside.

    Raises:
        ResetRefused: another connection, such as a served application's, held a table past the lock timeout.
    """
    _empty_catalog(connection, lock_timeout_milliseconds=lock_timeout_milliseconds)
    _logger.info("Recreating the content store...")
    _recreate_empty(library_root / OBJECTS_DIRECTORY_NAME)


def _empty_catalog(connection: Connection, *, lock_timeout_milliseconds: int) -> None:
    preparer = connection.dialect.identifier_preparer
    tables = ", ".join(preparer.format_table(table) for table in metadata.sorted_tables)
    _logger.info("Emptying %d catalog tables...", len(metadata.sorted_tables))
    try:
        with start_batch(connection):
            connection.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_milliseconds)}"))
            connection.execute(text(f"TRUNCATE TABLE {tables}"))
            for sequence in CATALOG_SEQUENCES:
                connection.execute(text(f"ALTER SEQUENCE {preparer.format_sequence(sequence)} RESTART"))
    except OperationalError as error:
        if not isinstance(error.orig, LockNotAvailable):
            raise
        raise ResetRefused(
            f"another connection held the catalog for over {lock_timeout_milliseconds} ms; "
            "stop the served application and any running pass, then reset again"
        ) from error


def _recreate_empty(directory: Path) -> None:
    retired = directory.with_name(directory.name + RETIRED_SUFFIX)
    if retired.is_dir():
        shutil.rmtree(retired)
    if directory.is_dir():
        directory.replace(retired)
    directory.mkdir(parents=True)
    if retired.is_dir():
        shutil.rmtree(retired)
