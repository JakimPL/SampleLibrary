from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.notes.backfill import extract_missing_notes
from sampleextract.notes.playback_rates import record_playback_rates

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one note-extraction pass over the catalog and report the result.

    The pass ends by folding every note event on file into the rate each sample is really heard at,
    which is what a listener hears when they play one, so the two always describe the same catalog.
    """
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = extract_missing_notes(config, connection, force=arguments.force)
        _logger.info("Folding note events into a playback rate per sample.")
        samples_rated = record_playback_rates(connection)

    _logger.info(
        "Discovered %d files: %d module(s) read for %d note event(s), "
        "%d already extracted, %d duplicate file(s), %d failed. "
        "Recorded a playback rate for %d sample(s).",
        summary.discovered,
        summary.read,
        summary.note_events,
        summary.already_extracted,
        summary.duplicate_files,
        len(summary.failures),
        samples_rated,
    )
    for failure in summary.failures:
        _logger.warning("Failed to read %s: %s", failure.path, failure.reason)

    if summary.failures:
        sys.exit(1)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read each cataloged module's patterns for the notes they play.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Read every module again, replacing the notes an earlier pass recorded.",
    )
    return parser.parse_args(argv)
