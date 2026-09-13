from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli, open_catalog_connection, redact_database_url, report_dry_run
from samplecore.storage.reset import reset_library

_logger = logging.getLogger(__name__)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Empty the configured library's catalog and content store. "
        "The next extraction pass starts from nothing; hand annotations stay.",
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Perform the reset; left out, the command names what it would empty."
    )
    return parser.parse_args(argv)


def main(argv: list[str], *, prog: str) -> None:
    """Empty the configured library once `--confirm` is given, and name what that would empty otherwise."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    target = f"the library at {config.library_root} (database: {redact_database_url(config.database_url)})"
    if not arguments.confirm:
        report_dry_run(
            "This would permanently delete every cataloged module, sample, relation, cloud coordinate, "
            f"experiment, and feature vector, and every stored audio object, for {target}."
        )
        return

    _logger.info("Resetting %s...", target)
    with open_catalog_connection(config.database_url) as connection:
        reset_library(connection, config.library_root)

    _logger.info("Done. The catalog and content store are empty; run extraction again to rebuild them.")
