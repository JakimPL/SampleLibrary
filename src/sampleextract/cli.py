from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.discovery import discover_modules
from sampleextract.progress import extraction_bar
from sampleextract.run import ExtractionSummary, run_extraction

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one extraction pass over the configured source directory and report it."""
    _parse_arguments(argv)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    paths = discover_modules(config.module_source_directory)
    with open_catalog_connection(config.database_url) as connection, extraction_bar(len(paths)) as progress:
        summary = run_extraction(config, connection, paths, progress=progress)

    _report(summary)
    if summary.failures:
        sys.exit(1)


def _report(summary: ExtractionSummary) -> None:
    """Say what the pass did, then name every file it could not read."""
    _logger.info(
        "Discovered %d modules: %d ingested, %d already known, %d ingested by another run, %d failed.",
        summary.discovered,
        len(summary.ingested),
        summary.skipped_existing,
        summary.ingested_elsewhere,
        len(summary.failures),
    )
    for failure in summary.failures:
        _logger.info("  %s: %s", failure.path, failure.reason)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract every module under the configured source directory.")
    return parser.parse_args(argv)
