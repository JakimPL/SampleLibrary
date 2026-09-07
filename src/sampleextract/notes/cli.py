from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.notes.backfill import extract_missing_notes

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one note-extraction pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = extract_missing_notes(config, connection, force=arguments.force)

    _logger.info(
        "Discovered %d modules: %d read for %d note event(s), %d already extracted, %d failed.",
        summary.discovered,
        summary.read,
        summary.note_events,
        summary.already_extracted,
        len(summary.failures),
    )
    for failure in summary.failures:
        _logger.warning("Failed to read %s: %s", failure.path, failure.reason)

    if summary.failures:
        sys.exit(1)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read each catalogued module's patterns for the notes they play.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Read every module again, replacing the notes an earlier pass recorded.",
    )
    return parser.parse_args(argv)
