from __future__ import annotations

import argparse

from samplecore.cli_support import bootstrap_cli
from samplecore.storage.database import connect
from sampleextract.thumbnail import compute_missing_thumbnails


def main(argv: list[str] | None = None) -> None:
    """Run one thumbnail backfill pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    connection = connect(config.resolved_database_path)
    try:
        summary = compute_missing_thumbnails(connection, config.library_root, force=arguments.force)
    finally:
        connection.close()

    print(
        f"{summary.catalogued} samples catalogued: {summary.computed} thumbnail(s) computed, "
        f"{summary.already_thumbnailed} already cached."
    )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute and cache a waveform-preview thumbnail for each sample.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute every sample's thumbnail, even one already cached -- use after changing the thumbnail size.",
    )
    return parser.parse_args(argv)
