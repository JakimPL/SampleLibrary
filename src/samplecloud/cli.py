from __future__ import annotations

import argparse
import logging

from samplecloud.backends.librosa_backend import LibrosaFeatureExtractor
from samplecloud.run import run_embedding
from samplecore.cli_support import bootstrap_cli, open_catalog_connection

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one embedding pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.resolved_database_path) as connection:
        summary = run_embedding(config, connection, LibrosaFeatureExtractor(), sample_limit=arguments.limit)

    _logger.info(
        "Extracted features for %d new samples (%d already known, %d catalogued). "
        "Reduced %d samples to 2D coordinates.",
        summary.extraction.newly_extracted,
        summary.extraction.already_extracted,
        summary.extraction.catalogued,
        summary.reduction.samples_reduced,
    )
    if summary.reduction.samples_orphaned:
        _logger.info(
            "Skipped %d cached feature vectors for samples no longer in the catalog.",
            summary.reduction.samples_orphaned,
        )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract sample features and reduce them to 2D cloud coordinates.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Extract features for only the first N unfeatured samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
