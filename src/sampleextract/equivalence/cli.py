from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.equivalence.detect import detect_equivalences

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one equivalence-detection pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        summary = detect_equivalences(connection, config.library_root, sample_limit=arguments.limit)

    _logger.info(
        "Considered %d samples: %d bit-depth variants, %d amplification variants, %d resampled variants.",
        summary.samples_considered,
        summary.bit_depth_relations,
        summary.amplification_relations,
        summary.resampled_relations,
    )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect bit-depth, amplification, and resampled equivalence classes in the catalog."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Consider only the first N catalogued samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
