from __future__ import annotations

import argparse
import logging
import sys
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand, command_parser
from samplecore.cli_support import (
    bootstrap_cli,
    integer_at_least,
    moment,
    open_catalog_connection,
    open_catalog_reader,
    report_dry_run,
)
from samplecore.exit_status import ExitStatus
from samplecore.labeling.vocabulary import read_vocabulary
from samplecore.models.annotation import AnnotationAnchor, ModuleSlotAnchor, SampleAnnotation, SampleFileAnchor
from samplecore.storage.repositories.annotation_history import PostgresAnnotationHistoryRepository
from sampleextract.annotations.history import MOMENT_FORMAT, history_lines
from sampleextract.annotations.relink import RelinkSummary, relink_annotations
from sampleextract.annotations.restore import RestorePlan, RestoreRefused, restore_annotations
from sampleextract.annotations.transfer import (
    DEFAULT_ANNOTATION_FILE,
    AnnotationFileRefused,
    export_annotations,
    import_annotations,
)
from sampleextract.annotations.vocabulary import vocabulary_lines

HISTORY_LIMIT: Final[int] = 50

_logger = logging.getLogger(__name__)


@unique
class AnnotationCommand(StrEnum):
    """The things this command does with hand annotations."""

    EXPORT = "export"
    IMPORT = "import"
    RELINK = "relink"
    VOCABULARY = "vocabulary"
    HISTORY = "history"
    RESTORE = "restore"

    @property
    def reads_only(self) -> bool:
        """Whether the command reports what the catalog holds, leaving every row as it is."""
        match self:
            case AnnotationCommand.EXPORT | AnnotationCommand.VOCABULARY | AnnotationCommand.HISTORY:
                return True
            case AnnotationCommand.IMPORT | AnnotationCommand.RELINK | AnnotationCommand.RESTORE:
                return False


def main(argv: list[str], *, prog: str) -> None:
    """Move hand annotations between the catalog and a file, reattach ones whose sample moved, list their wording,
    show how they changed, or bring them back to how they stood at a moment."""
    arguments = _parse_arguments(argv, prog=prog)
    command = AnnotationCommand(arguments.command)
    config = bootstrap_cli()
    open_catalog = open_catalog_reader if command.reads_only else open_catalog_connection
    with open_catalog(config.catalog_url()) as connection:
        try:
            _run(command, arguments, connection)
        except AnnotationFileRefused as error:
            _logger.error("Moved nothing: %s.", error)
            sys.exit(ExitStatus.REFUSED)
        except RestoreRefused as error:
            _logger.error("Restored nothing: %s.", error)
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
        case AnnotationCommand.HISTORY:
            changes = PostgresAnnotationHistoryRepository(connection).changes(
                sample_hash=arguments.sample, since=arguments.since, limit=arguments.limit
            )
            print("\n".join(history_lines(changes)))
        case AnnotationCommand.RESTORE:
            _report_restore(
                restore_annotations(connection, moment=arguments.at, apply=arguments.confirm), arguments.confirm
            )


def _report_restore(plan: RestorePlan, applied: bool) -> None:
    description = (
        f"the labels as they stood at {plan.moment.astimezone():{MOMENT_FORMAT}}: {len(plan.upserts)} sample(s) "
        f"written, {len(plan.removals)} cleared, {plan.unchanged} already so"
    )
    if applied:
        _logger.info("Restored %s.", description)
    else:
        report_dry_run(f"Restoring would bring back {description}.")


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
    parser = command_parser(
        prog=prog,
        description="Move hand-made sample annotations in and out of the catalog, list their history, restore them.",
    )
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

    history_parser = add_subcommand(
        commands,
        AnnotationCommand.HISTORY.value,
        summary="List the latest changes to the annotations, oldest first, each with the moment it was made.",
    )
    history_parser.add_argument("--sample", type=str, default=None, help="The hash of the one sample to list.")
    history_parser.add_argument(
        "--since", type=moment, default=None, help="The earliest moment to list, as 2026-09-26 21:30."
    )
    history_parser.add_argument(
        "--limit", type=integer_at_least(1), default=HISTORY_LIMIT, help="How many changes to list at most."
    )

    restore_parser = add_subcommand(
        commands,
        AnnotationCommand.RESTORE.value,
        summary="Bring every annotation back to how it stood at a moment the history covers.",
    )
    restore_parser.add_argument(
        "--at", type=moment, required=True, help="The moment to bring the annotations back to, as 2026-09-26 21:30."
    )
    restore_parser.add_argument("--confirm", action="store_true", help="Carry the restore out.")
    return parser.parse_args(argv)
