from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.digests import stat_digest
from samplecore.exit_status import ExitStatus
from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository
from sampleextract.corpus import CorpusOutcome, extract_corpus
from sampleextract.discovery import Discovery, discover_modules
from sampleextract.parallel.cli import add_workers_argument, raise_worker_errors
from sampleextract.prune import PruneRefused, prune_gone_modules
from sampleextract.run import ExtractionSummary

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one extraction pass over the configured source directory, report it, and prune when asked.

    A pass that prunes leaves a record of the collection it read, a digest of every module file's
    path, size and write time, so a later pass finding the collection exactly so ends at once: the
    catalog already mirrors it. Any pass that goes ahead drops that record first, since what it adds
    changes what the catalog mirrors, and `--force` goes ahead whatever the record says.

    Raises:
        SystemExit: the source directory is missing, or a prune was asked for and refused.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    discovery = _discovery_or_exit(config)
    collection_digest = stat_digest(config.module_source_directory, discovery.paths)
    if not _goes_ahead(config, collection_digest, force=arguments.force):
        _logger.info("The module collection is as the last complete pass left it, so there is nothing to extract.")
        return

    outcome = extract_corpus(config, discovery, workers=arguments.workers)
    _report(outcome.summary)
    raise_worker_errors(outcome.worker_errors)
    if arguments.prune:
        _prune(config, outcome)
        _record_the_complete_pass(config, collection_digest)


def _discovery_or_exit(config: LibraryConfig) -> Discovery:
    """The module files under the source directory.

    Raises:
        SystemExit: the source directory is missing or names a file.
    """
    try:
        return discover_modules(config.module_source_directory)
    except (FileNotFoundError, NotADirectoryError) as error:
        _logger.error("%s; set module_source_directory to your module collection.", error)
        sys.exit(ExitStatus.REFUSED)


def _goes_ahead(config: LibraryConfig, collection_digest: str, *, force: bool) -> bool:
    """Whether the pass has anything to do, dropping the record of the last complete pass when it does."""
    with open_catalog_connection(config.database_url) as connection:
        passes = PostgresPassCompletionRepository(connection)
        if not force and passes.finished_over(PassKind.MODULES, collection_digest):
            return False
        with start_batch(connection):
            passes.forget(PassKind.MODULES)
    return True


def _record_the_complete_pass(config: LibraryConfig, collection_digest: str) -> None:
    """Record the collection a pruned pass mirrors, once a second listing finds it as the pass found it."""
    if stat_digest(config.module_source_directory, _discovery_or_exit(config).paths) != collection_digest:
        _logger.info("The collection changed while the pass read it, so the next pass reads it again.")
        return
    with open_catalog_connection(config.database_url) as connection, start_batch(connection):
        PostgresPassCompletionRepository(connection).record(
            PassCompletion(kind=PassKind.MODULES, digest=collection_digest, completed_at=datetime.now(UTC))
        )


def _report(summary: ExtractionSummary) -> None:
    """Say what the pass did, then name every file it could not take in.

    A module that fails describes the collection, so it goes out as a warning and the pass still
    ends a success: what did land is cataloged, and the stages that follow extraction run on it.
    """
    _logger.info(
        "Discovered %d modules: %d ingested, %d already known, %d ingested by another worker, %d failed.",
        summary.discovered,
        len(summary.ingested),
        summary.skipped_existing,
        summary.ingested_elsewhere,
        len(summary.failures),
    )
    for failure in summary.failures:
        _logger.warning("Could not %s %s: %s", failure.stage.value, failure.path, failure.reason)


def _prune(config: LibraryConfig, outcome: CorpusOutcome) -> None:
    with open_catalog_connection(config.database_url) as connection:
        try:
            summary = prune_gone_modules(config, connection, outcome)
        except PruneRefused as error:
            _logger.error("Pruned nothing: %s.", error)
            sys.exit(ExitStatus.REFUSED)

    _logger.info(
        "Pruned %d module(s) whose file is gone, %d sample(s) nothing else holds, and %d stored object(s).",
        summary.modules_removed,
        summary.samples_removed,
        summary.objects_removed,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Catalog every module under the configured source directory.")
    add_workers_argument(parser, work="the corpus")
    parser.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Afterwards, remove the modules whose files are gone and the samples no module holds; "
            "hand annotations stay for `annotations relink`."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Read the whole collection even when it is as the last complete pass left it.",
    )
    return parser.parse_args(argv)
