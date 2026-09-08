from __future__ import annotations

import logging
import sys

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.run import run_extraction

_logger = logging.getLogger(__name__)


def main() -> None:
    """Run one extraction pass over the configured module source directory and report the result."""
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    with open_catalog_connection(config.database_url) as connection:
        summary = run_extraction(config, connection)

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

    if summary.failures:
        sys.exit(1)
