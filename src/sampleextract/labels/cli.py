from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique
from pathlib import Path

from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from sampleextract.labels.relink import RelinkSummary, relink_labels
from sampleextract.labels.transfer import DEFAULT_LABEL_FILE, export_labels, import_labels

_logger = logging.getLogger(__name__)


@unique
class LabelCommand(StrEnum):
    """The three things this command does with hand labels."""

    EXPORT = "export"
    IMPORT = "import"
    RELINK = "relink"


def main(argv: list[str] | None = None) -> None:
    """Move hand labels between the catalog and a file, or reattach ones whose sample has moved."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        _run(LabelCommand(arguments.command), arguments, connection)


def _run(command: LabelCommand, arguments: argparse.Namespace, connection: Connection) -> None:
    match command:
        case LabelCommand.EXPORT:
            summary = export_labels(connection, path=arguments.path)
            _logger.info("Wrote %d label(s) to %s.", summary.labels, summary.path)
        case LabelCommand.IMPORT:
            summary = import_labels(connection, path=arguments.path)
            _logger.info("Read %d label(s) from %s.", summary.labels, summary.path)
        case LabelCommand.RELINK:
            _report_relink(relink_labels(connection))


def _report_relink(summary: RelinkSummary) -> None:
    """Report a relink pass, naming every label a person still has to decide about."""
    _logger.info(
        "Checked %d label(s): %d named a sample the catalog no longer holds, %d relinked.",
        summary.checked,
        summary.stale,
        summary.relinked,
    )
    for label in summary.unresolved:
        _logger.warning(
            "Left alone: %r on %s, whose slot %d/%d in %s is no longer catalogued.",
            label.label,
            label.sample_hash,
            label.occurrence.instrument_index,
            label.occurrence.sample_slot,
            label.module_filename,
        )

    if summary.unresolved:
        sys.exit(1)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move hand-chosen sample labels in and out of the catalog.")
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = commands.add_parser(
        LabelCommand.EXPORT.value, help="Write every label to a JSONL file, the copy that outlives the database."
    )
    export_parser.add_argument("--path", type=Path, default=DEFAULT_LABEL_FILE, help="Where to write the labels.")

    import_parser = commands.add_parser(
        LabelCommand.IMPORT.value, help="Read labels from a JSONL file, merging them into whatever is on file."
    )
    import_parser.add_argument("--path", type=Path, default=DEFAULT_LABEL_FILE, help="Where to read the labels from.")

    commands.add_parser(
        LabelCommand.RELINK.value,
        help="Reattach labels whose sample hash the catalog no longer holds, through their anchors.",
    )
    return parser.parse_args(argv)
