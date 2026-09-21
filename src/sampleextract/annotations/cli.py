from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique
from pathlib import Path

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand, command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection, open_catalog_reader
from samplecore.exit_status import ExitStatus
from samplecore.labeling.vocabulary import read_vocabulary
from samplecore.models.annotation import AnnotationAnchor, ModuleSlotAnchor, SampleAnnotation, SampleFileAnchor
from sampleextract.annotations.relink import RelinkSummary, relink_annotations
from sampleextract.annotations.transfer import (
    DEFAULT_ANNOTATION_FILE,
    AnnotationFileRefused,
    export_annotations,
    import_annotations,
)
from sampleextract.annotations.vocabulary import vocabulary_lines

_logger = logging.getLogger(__name__)


@unique
class AnnotationCommand(StrEnum):
    """The four things this command does with hand annotations."""

    EXPORT = "export"
    IMPORT = "import"
    RELINK = "relink"
    VOCABULARY = "vocabulary"

    @property
    def reads_only(self) -> bool:
        """Whether the command reports what the catalog holds, leaving every row as it is."""
        match self:
            case AnnotationCommand.EXPORT | AnnotationCommand.VOCABULARY:
                return True
            case AnnotationCommand.IMPORT | AnnotationCommand.RELINK:
                return False


def main(argv: list[str], *, prog: str) -> None:
    """Move hand annotations between the catalog and a file, reattach ones whose sample moved, or list their wording."""
    arguments = _parse_arguments(argv, prog=prog)
    command = AnnotationCommand(arguments.command)
    config = bootstrap_cli()
    open_catalog = open_catalog_reader if command.reads_only else open_catalog_connection
    with open_catalog(config.database_url) as connection:
        try:
            _run(command, arguments, connection)
        except AnnotationFileRefused as error:
            _logger.error("Moved nothing: %s.", error)
            sys.exit(ExitStatus.REFUSED)


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
        case AnnotationCommand.VOCABULARY:
            print("\n".join(vocabulary_lines(read_vocabulary(connection))))


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
            "Left alone: %s on %s, whose %s is no longer cataloged.",
            _describe(annotation),
            annotation.sample_hash,
            _describe_anchor(annotation.anchor),
        )
    for annotation in summary.conflicting:
        _logger.warning(
            "Left alone: %s on %s, whose %s now holds a sample with a decision of its own.",
            _describe(annotation),
            annotation.sample_hash,
            _describe_anchor(annotation.anchor),
        )


def _describe_anchor(anchor: AnnotationAnchor) -> str:
    """Where an annotation was anchored, in the words a person would find the place by."""
    match anchor:
        case ModuleSlotAnchor():
            return (
                f"slot {anchor.occurrence.instrument_index}/{anchor.occurrence.sample_slot} in {anchor.module_filename}"
            )
        case SampleFileAnchor():
            return f"file {anchor.location.path}"


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


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Move hand-made sample annotations in and out of the catalog.")
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = add_subcommand(
        commands,
        AnnotationCommand.EXPORT.value,
        summary="Write every annotation to a JSONL file, the copy that outlives the database.",
    )
    export_parser.add_argument(
        "--path", type=Path, default=DEFAULT_ANNOTATION_FILE, help="Where to write the annotations."
    )

    import_parser = add_subcommand(
        commands,
        AnnotationCommand.IMPORT.value,
        summary="Read annotations from a JSONL file, merging them into whatever is on file.",
    )
    import_parser.add_argument(
        "--path", type=Path, default=DEFAULT_ANNOTATION_FILE, help="Where to read the annotations from."
    )

    add_subcommand(
        commands,
        AnnotationCommand.RELINK.value,
        summary="Reattach annotations whose sample hash the catalog no longer holds, through their anchors.",
    )
    add_subcommand(
        commands,
        AnnotationCommand.VOCABULARY.value,
        summary="List every tag in use as a tree with counts, and the wording worth a second look.",
    )
    return parser.parse_args(argv)
