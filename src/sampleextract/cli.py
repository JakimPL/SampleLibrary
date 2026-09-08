from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.sharding import WHOLE, Shard, parse_shard
from sampleextract.run import ExtractionSummary, run_extraction

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one extraction pass over this run's share of the source directory and report it."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    with open_catalog_connection(config.database_url) as connection:
        summary = run_extraction(config, connection, shard=arguments.shard)

    _report(summary)
    if summary.failures:
        sys.exit(1)


def _report(summary: ExtractionSummary) -> None:
    """Say what the run did, naming its shard where the run was only part of the work."""
    _logger.info(
        "%s %d modules: %d ingested, %d already known, %d ingested by another run, %d failed.",
        _describe(summary.shard),
        summary.discovered,
        len(summary.ingested),
        summary.skipped_existing,
        summary.ingested_elsewhere,
        len(summary.failures),
    )
    for failure in summary.failures:
        _logger.info("  %s: %s", failure.path, failure.reason)


def _describe(shard: Shard) -> str:
    """How a run names the work it covered: a whole corpus, or the share it took of one."""
    return "Discovered" if shard.is_whole else f"Shard {shard} discovered"


def _shard_argument(value: str) -> Shard:
    """Read the ``--shard`` value, reporting a bad one the way argparse reports its own.

    Raises:
        argparse.ArgumentTypeError: the value names no real share of a split.
    """
    try:
        return parse_shard(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract every module under the configured source directory.")
    parser.add_argument(
        "--shard",
        type=_shard_argument,
        default=WHOLE,
        help=(
            "This run's share of the corpus, as index/count -- 0/4 through 3/4 split it between four runs, "
            "which may sit on different machines pointed at one catalog. Defaults to the whole corpus."
        ),
    )
    return parser.parse_args(argv)
