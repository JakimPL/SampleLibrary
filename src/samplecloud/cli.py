from __future__ import annotations

import argparse

from samplecloud.backends.librosa_backend import LibrosaFeatureExtractor
from samplecloud.run import run_embedding
from samplecore.cli_support import bootstrap_cli
from samplecore.storage.database import connect


def main(argv: list[str] | None = None) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    connection = connect(config.resolved_database_path)
    try:
        summary = run_embedding(config, connection, LibrosaFeatureExtractor(), sample_limit=arguments.limit)
    finally:
        connection.close()

    message = (
        f"Extracted features for {summary.extraction.newly_extracted} new samples "
        f"({summary.extraction.already_extracted} already known, {summary.extraction.catalogued} catalogued). "
        f"Reduced {summary.reduction.samples_reduced} samples to 2D coordinates."
    )
    if summary.reduction.samples_orphaned:
        message += (
            f" Skipped {summary.reduction.samples_orphaned} cached feature vectors for samples no longer "
            "in the catalog."
        )
    print(message)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract sample features and reduce them to 2D cloud coordinates.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Extract features for only the first N unfeatured samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
