from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique

from samplecore.cli_parsing import add_subcommand, command_parser
from samplecore.cli_support import bootstrap_cli, configure_console_output_encoding, configure_logging
from samplecore.config import ConfigurationError, create_config_file, resolve_config_path
from samplecore.storage.cluster.provisioning import ProvisioningError, ProvisioningSummary, provision

_logger = logging.getLogger(__name__)


@unique
class SetupCommand(StrEnum):
    """The two things standing between a fresh clone and a working library."""

    CONFIG = "config"
    DATABASE = "database"


def main(argv: list[str], *, prog: str) -> None:
    """Put a config file in place, or prepare the Postgres server the configuration names."""
    arguments = _parse_arguments(argv, prog=prog)
    match SetupCommand(arguments.command):
        case SetupCommand.CONFIG:
            _run_config()
        case SetupCommand.DATABASE:
            _run_database()


def _run_config() -> None:
    """Put a config file where commands read one, leaving one already there exactly as it is.

    That place is the one `--config` names, then `SAMPLELIBRARY_CONFIG`, then the repository root.

    Raises:
        SystemExit: the example this copies from is absent.
    """
    configure_console_output_encoding()
    configure_logging()
    config_path = resolve_config_path()
    try:
        created = create_config_file(config_path)
    except ConfigurationError as error:
        _logger.error("%s", error)
        sys.exit(1)

    if created:
        _logger.warning("Wrote %s. Open it and fill in your own paths before running anything else.", config_path)
    else:
        _logger.info("Keeping the config file already at %s.", config_path)


def _run_database() -> None:
    """Create the role and databases the configuration expects, then report what that took.

    Raises:
        SystemExit: the server refused a connection or a statement, in which case the steps that
            would let it succeed have been reported.
    """
    config = bootstrap_cli()
    try:
        summary = provision(config.database_url)
    except ProvisioningError as error:
        _report_obstacle(error)
        sys.exit(1)

    _report(summary)


def _report(summary: ProvisioningSummary) -> None:
    """Name every object this pass looked for, and say which of them it added."""
    _logger.info("Postgres at %s, as role %r.", summary.server, summary.role)
    _logger.info("Created the role." if summary.role_created else "The role was already there.")
    for outcome in summary.databases:
        _logger.info("Created database %r." if outcome.created else "Database %r was already there.", outcome.name)

    _logger.info("Catalog and curation schemas are ready in %s.", " and ".join(summary.schemas_prepared))
    if not summary.role_creates_databases:
        _logger.warning(
            "Role %r may not create databases, which the test suite needs for a database per worker. Grant it that:",
            summary.role,
        )
        _logger.warning('    sudo -u postgres psql -c "ALTER ROLE %s CREATEDB"', summary.role)

    added = summary.role_created or any(outcome.created for outcome in summary.databases)
    _logger.info("Done." if added else "Done. Everything was already in place, so the server is as it was.")


def _report_obstacle(error: ProvisioningError) -> None:
    """Say what the server refused, then the steps that would let it succeed.

    The whole report goes out as one log record, so the timestamp every record carries lands once
    at the top rather than down the left of a command a person is about to copy.
    """
    _logger.error("%s", "\n".join((str(error), "", *error.remedy)))


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Put a config file in place, or prepare the databases it names.")
    commands = parser.add_subparsers(dest="command", required=True)

    add_subcommand(
        commands,
        SetupCommand.CONFIG.value,
        summary="Copy config.example.toml to config.toml, keeping any config file already there.",
    )
    add_subcommand(
        commands,
        SetupCommand.DATABASE.value,
        summary="Create the role and the three databases this project expects, where they are missing.",
    )
    return parser.parse_args(argv)
