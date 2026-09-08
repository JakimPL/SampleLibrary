from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique
from pathlib import Path

from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.models.annotation import SampleAnnotation
from sampleextract.annotations.relink import RelinkSummary, relink_annotations
from sampleextract.annotations.transfer import DEFAULT_ANNOTATION_FILE, export_annotations, import_annotations

_logger = logging.getLogger(__name__)


@unique
class AnnotationCommand(StrEnum):
    """The three things this command does with hand annotations."""

    EXPORT = "export"
    IMPORT = "import"
    RELINK = "relink"


def main(argv: list[str] | None = None) -> None:
    """Move hand annotations between the catalog and a file, or reattach ones whose sample moved."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        _run(AnnotationCommand(arguments.command), arguments, connection)


def _run(command: AnnotationCommand, arguments: argparse.Namespace, connection: Connection) -> None:
    match command:
        case AnnotationCommand.EXPORT:
            summary = export_annotations(connection, path=arguments.path)
            _logger.info("Wrote %d annotation(s) to %s.", summary.annotations, summary.path)
        case AnnotationCommand.IMPORT:
            summary = import_annotations(connection, path=arguments.path)
            _logger.info("Read %d annotation(s) from %s.", summary.annotations, summary.path)
        case AnnotationCommand.RELINK:
            _report_relink(relink_annotations(connection))


def _report_relink(summary: RelinkSummary) -> None:
    """Report a relink pass, naming every annotation a person still has to decide about."""
    _logger.info(
        "Checked %d annotation(s): %d named a sample the catalog no longer holds, %d relinked.",
        summary.checked,
        summary.stale,
        summary.relinked,
    )
    for annotation in summary.unresolved:
        _logger.warning(
            "Left alone: %s on %s, whose slot %d/%d in %s is no longer cataloged.",
            _describe(annotation),
            annotation.sample_hash,
            annotation.occurrence.instrument_index,
            annotation.occurrence.sample_slot,
            annotation.module_filename,
        )

    if summary.unresolved:
        sys.exit(1)


def _describe(annotation: SampleAnnotation) -> str:
    """What an annotation says, in the words a person would recognize it by.

    An annotation may record a rating or a favorite mark and no wording at all, so each decision it
    does carry is named; the label leads where there is one, being what identifies the sample.
    """
    decisions = []
    if annotation.label is not None:
        decisions.append(repr(annotation.label))
    if annotation.rating is not None:
        decisions.append(f"rated {annotation.rating}")
    if annotation.favorite:
        decisions.append("favorite")

    return ", ".join(decisions)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move hand-made sample annotations in and out of the catalog.")
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = commands.add_parser(
        AnnotationCommand.EXPORT.value,
        help="Write every annotation to a JSONL file, the copy that outlives the database.",
    )
    export_parser.add_argument(
        "--path", type=Path, default=DEFAULT_ANNOTATION_FILE, help="Where to write the annotations."
    )

    import_parser = commands.add_parser(
        AnnotationCommand.IMPORT.value,
        help="Read annotations from a JSONL file, merging them into whatever is on file.",
    )
    import_parser.add_argument(
        "--path", type=Path, default=DEFAULT_ANNOTATION_FILE, help="Where to read the annotations from."
    )

    commands.add_parser(
        AnnotationCommand.RELINK.value,
        help="Reattach annotations whose sample hash the catalog no longer holds, through their anchors.",
    )
    return parser.parse_args(argv)
