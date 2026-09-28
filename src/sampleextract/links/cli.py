from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from sampleextract.discovery import require_module_source_directory
from sampleextract.links.file import LinkFileRefused
from sampleextract.links.importing import NAMED_SKIPS, LinkImportSummary, import_links
from sampleextract.links.messages import (
    FILE_MISSING,
    IMPORTED_NOTHING,
    MORE_SKIPPED,
    NO_SOURCE_DIRECTORY,
    NOT_CATALOGED,
    RECORDED,
    SOURCE_DIRECTORY_MISSING,
)

DESCRIPTION: Final[str] = "Read a CSV of module locations and page links, recording each cataloged module's link."

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Record the page each cataloged module came from, from a CSV of module locations and page links.

    Raises:
        SystemExit: no module collection is configured or it is missing, or the file is refused.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    source_directory = _source_directory_or_exit(config)
    with open_catalog_connection(config.catalog_url()) as connection:
        try:
            summary = import_links(connection, path=arguments.path, source_directory=source_directory)
        except LinkFileRefused as error:
            _logger.error("%s", IMPORTED_NOTHING.format(problem=error))
            sys.exit(ExitStatus.REFUSED)
    _report(summary)


def _source_directory_or_exit(config: LibraryConfig) -> Path:
    """The module collection the file's locations are read under.

    Raises:
        SystemExit: no collection is configured, or the configured one is missing or names a file.
    """
    if config.module_source_directory is None:
        _logger.error("%s", NO_SOURCE_DIRECTORY)
        sys.exit(ExitStatus.REFUSED)
    try:
        return require_module_source_directory(config.module_source_directory)
    except (FileNotFoundError, NotADirectoryError) as error:
        _logger.error("%s", SOURCE_DIRECTORY_MISSING.format(problem=error))
        sys.exit(ExitStatus.REFUSED)


def _report(summary: LinkImportSummary) -> None:
    """Say what was recorded, and name the first locations of each kind passed over."""
    _logger.info(
        "%s",
        RECORDED.format(
            recorded=summary.recorded,
            path=summary.path,
            missing=len(summary.missing),
            uncataloged=len(summary.uncataloged),
        ),
    )
    _warn_each(summary.missing, FILE_MISSING)
    _warn_each(summary.uncataloged, NOT_CATALOGED)


def _warn_each(locations: tuple[str, ...], message: str) -> None:
    for location in locations[:NAMED_SKIPS]:
        _logger.warning("%s", message.format(location=location))
    if len(locations) > NAMED_SKIPS:
        _logger.warning("%s", MORE_SKIPPED.format(count=len(locations) - NAMED_SKIPS))


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description=DESCRIPTION)
    parser.add_argument("path", type=Path, help="The CSV of module locations and page links.")
    return parser.parse_args(argv)
