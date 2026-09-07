from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, confirmed, open_catalog_connection
from samplecore.storage.audio_store import OBJECTS_DIRECTORY_NAME
from samplecore.storage.database import metadata

_logger = logging.getLogger(__name__)


def reset_library(connection: Connection, library_root: Path) -> None:
    """Empty every catalog table (feature vectors and experiments included) and the content store.

    The database and its schema are left in place, ready for a fresh extraction pass to rebuild
    them from nothing. Tables are cleared one at a time, each committed before the next starts, in
    reverse dependency order (children before parents) -- Postgres's own foreign-key checking does
    not reliably see an earlier delete in the same still-open transaction once composite keys are
    involved, so a single all-or-nothing batch is not available here the way
    ``detect_equivalences``'s own transaction is. The content store's ``objects`` directory is
    removed and recreated empty, rather than left for a fresh run to overwrite piecemeal --
    content addressing means a stale object could otherwise survive under a hash extraction never
    revisits again.
    """
    for table in reversed(metadata.sorted_tables):
        _logger.info("Emptying %s...", table.name)
        connection.execute(table.delete())
        connection.commit()

    _logger.info("Recreating the content store...")
    _recreate_empty(library_root / OBJECTS_DIRECTORY_NAME)


def _recreate_empty(directory: Path) -> None:
    if directory.is_dir():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Permanently empty the configured library's catalog and content store, so the "
        "next extraction pass starts from nothing. Destructive and irreversible."
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Actually perform the reset. Without this flag, nothing is changed."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    if not confirmed(
        argv,
        _parse_arguments,
        "This would permanently delete every catalogued module, sample, relation, cloud "
        "coordinate, experiment, and feature vector, and every stored audio object, for the "
        "library named in your config.toml.",
    ):
        return

    config = bootstrap_cli()
    _logger.info("Resetting the library at %s (database: %s)...", config.library_root, config.database_url)
    with open_catalog_connection(config.database_url) as connection:
        reset_library(connection, config.library_root)

    _logger.info("Done. The catalog and content store are empty; run extraction again to rebuild them.")


if __name__ == "__main__":
    main()
