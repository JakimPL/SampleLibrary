from __future__ import annotations

import argparse
import logging

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_audio, positive_integer
from sampleextract.equivalence.detect import detect_equivalences

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one equivalence-detection pass over the catalog and report the result."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_audio(config) as (connection, audio):
        summary = detect_equivalences(connection, audio, sample_limit=arguments.limit)

    _logger.info(
        "Considered %d samples (%d silent, %d with no file to read now, %d pairs left for a later pass), "
        "scored %d gain and %d resampled candidates: "
        "%d bit-depth variants, %d amplification variants, %d resampled variants.",
        summary.samples_considered,
        summary.silent_samples,
        summary.unavailable_samples,
        summary.unavailable_pairs,
        summary.gain_candidates,
        summary.resampled_candidates,
        summary.bit_depth_relations,
        summary.amplification_relations,
        summary.resampled_relations,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Detect bit-depth, amplification and resampled variants among the cataloged samples."
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        default=None,
        help="Consider only the first N cataloged samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
