from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli, open_catalog_connection, positive_integer
from sampleextract.equivalence.detect import detect_equivalences

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one equivalence-detection pass over the catalog and report the result."""
    arguments = _parse_arguments(argv, prog=prog)
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


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Detect bit-depth, amplification and resampled variants among the cataloged samples."
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        default=None,
        help="Consider only the first N cataloged samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
