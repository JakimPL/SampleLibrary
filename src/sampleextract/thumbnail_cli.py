from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.thumbnail import compute_missing_thumbnails

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one thumbnail backfill pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = compute_missing_thumbnails(connection, config.library_root, force=arguments.force)

    _logger.info(
        "%d samples catalogued: %d thumbnail(s) computed, %d already cached.",
        summary.catalogued,
        summary.computed,
        summary.already_thumbnailed,
    )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute and cache a waveform-preview thumbnail for each sample.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute every sample's thumbnail, even one already cached -- use after changing the thumbnail size.",
    )
    return parser.parse_args(argv)
