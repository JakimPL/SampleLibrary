from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.exit_status import ExitStatus
from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository
from sampleextract.notes.backfill import extract_missing_notes
from sampleextract.notes.playback_rates import record_playback_rates
from sampleextract.parsing import FailureStage

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one note-extraction pass over the catalog and report the result.

    The pass ends by folding every note event on file into the rate each sample is really heard at,
    which is what a listener hears when they play one, so the two always describe the same catalog.
    A module whose patterns cannot be parsed describes the collection, so it goes out as a warning
    and the pass still ends a success. A pass that read every file it reached records the modules it
    covered, so a later pass over the same set of modules ends at once; `--force` reads them all again.

    Raises:
        SystemExit: the source directory is missing.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_connection(config.catalog_url()) as connection:
        modules = PostgresModuleRepository(connection)
        passes = PostgresPassCompletionRepository(connection)
        membership = modules.membership_digest()
        if not arguments.force and passes.finished_over(PassKind.NOTES, membership):
            _logger.info("The cataloged modules are the ones the last complete pass read, so there is nothing to read.")
            return
        with start_batch(connection):
            passes.forget(PassKind.NOTES)
        try:
            summary = extract_missing_notes(config, connection, force=arguments.force)
        except (FileNotFoundError, NotADirectoryError) as error:
            _logger.error("%s; set module_source_directory to your module collection.", error)
            sys.exit(ExitStatus.REFUSED)
        _logger.info("Folding note events into a playback rate per sample.")
        samples_rated = record_playback_rates(connection)
        unread = [failure for failure in summary.failures if failure.stage is FailureStage.READ]
        if not unread and modules.membership_digest() == membership:
            with start_batch(connection):
                passes.record(PassCompletion(kind=PassKind.NOTES, digest=membership, completed_at=datetime.now(UTC)))

    _logger.info(
        "Discovered %d files: %d module(s) read for %d note event(s), "
        "%d already extracted, %d duplicate file(s), %d failed. "
        "Recorded a playback rate for %d sample(s).",
        summary.discovered,
        summary.read,
        summary.note_events,
        summary.already_extracted,
        summary.duplicate_files,
        len(summary.failures),
        samples_rated,
    )
    for failure in summary.failures:
        _logger.warning("Could not %s %s: %s", failure.stage.value, failure.path, failure.reason)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Read the notes each module plays, and the rate each sample is heard at."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Read every module again, replacing the notes an earlier pass recorded.",
    )
    return parser.parse_args(argv)
