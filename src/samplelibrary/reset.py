from __future__ import annotations

import argparse
import logging
from typing import Final

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import (
    bootstrap_cli,
    ending_in_one_line,
    open_catalog_connection,
    redact_database_url,
    report_dry_run,
)
from samplecore.storage.reset import ResetRefused, reset_library

EMPTIED: Final[str] = (
    "every cataloged module, sample, note event, relation, playback rate, cloud coordinate and promotion, "
    "experiment, feature vector and category, and every stored audio object"
)
KEPT: Final[str] = "hand annotations, fitted models, grid caches, training runs and the MLflow record"
REFILLING_PASSES: Final[str] = "`samplelibrary pipeline run`, which builds every step again and relinks the annotations"

_logger = logging.getLogger(__name__)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog,
        description="Empty the configured library's catalog and content store. "
        "The next extraction pass starts from nothing; hand annotations, models, caches and runs stay.",
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Perform the reset; left out, the command names what it would empty."
    )
    return parser.parse_args(argv)


def main(argv: list[str], *, prog: str) -> None:
    """Empty the configured library once `--confirm` is given, and name what that would empty otherwise."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    target = f"the library at {config.library_root} (database: {redact_database_url(config.catalog_url())})"
    if not arguments.confirm:
        report_dry_run(f"This would permanently delete {EMPTIED} for {target}; {KEPT} stay.")
        return

    _logger.info("Resetting %s...", target)
    with (
        open_catalog_connection(config.catalog_url()) as connection,
        ending_in_one_line("Reset nothing", (ResetRefused,)),
    ):
        reset_library(connection, config.library_root)

    _logger.info("Done. The catalog and content store are empty; %s stay.", KEPT)
    _logger.info("To fill the library again: %s.", REFILLING_PASSES)
