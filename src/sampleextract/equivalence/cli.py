from __future__ import annotations

import argparse

from samplecore.storage.database import connect
from sampleextract.cli_support import load_config_or_exit
from sampleextract.equivalence.detect import detect_equivalences


def main(argv: list[str] | None = None) -> None:
    """Run one equivalence-detection pass over the catalog and report the result."""
    arguments = _parse_arguments(argv)
    config = load_config_or_exit()
    connection = connect(config.resolved_database_path)
    try:
        summary = detect_equivalences(connection, config.library_root, sample_limit=arguments.limit)
    finally:
        connection.close()

    print(
        f"Considered {summary.samples_considered} samples: "
        f"{summary.bit_depth_relations} bit-depth variants, {summary.resampled_relations} resampled variants."
    )


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect bit-depth and resampled equivalence classes in the catalog.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Consider only the first N catalogued samples, for a quick run over a small slice.",
    )
    return parser.parse_args(argv)
