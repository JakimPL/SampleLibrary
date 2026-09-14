from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_support import bootstrap_cli, integer_at_least, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.scalars import MINIMUM_WORKER_COUNT
from sampleextract.parallel.supervisor import CorpusOutcome, default_worker_count, extract_corpus
from sampleextract.prune import PruneRefused, prune_gone_modules
from sampleextract.run import ExtractionSummary

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one extraction pass over the configured source directory, report it, and prune when asked.

    Raises:
        SystemExit: the source directory is missing, or a prune was asked for and refused.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    try:
        outcome = extract_corpus(config, workers=arguments.workers)
    except (FileNotFoundError, NotADirectoryError) as error:
        _logger.error("%s; set module_source_directory to your module collection.", error)
        sys.exit(1)

    _report(outcome.summary)
    _raise_a_worker_error(outcome)
    if arguments.prune:
        _prune(config, outcome)


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


def _raise_a_worker_error(outcome: CorpusOutcome) -> None:
    """Report every share that stopped, then raise the first error, which is what the run ends with."""
    for error in outcome.worker_errors:
        _logger.error("A worker process stopped: %s", error, exc_info=error)
    if outcome.worker_errors:
        raise outcome.worker_errors[0]


def _prune(config: LibraryConfig, outcome: CorpusOutcome) -> None:
    with open_catalog_connection(config.database_url) as connection:
        try:
            summary = prune_gone_modules(config, connection, outcome)
        except PruneRefused as error:
            _logger.error("Pruned nothing: %s.", error)
            sys.exit(1)

    _logger.info(
        "Pruned %d module(s) whose file is gone, %d sample(s) no module holds, and %d stored object(s).",
        summary.modules_removed,
        summary.samples_removed,
        summary.objects_removed,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Catalog every module under the configured source directory."
    )
    parser.add_argument(
        "--workers",
        type=integer_at_least(MINIMUM_WORKER_COUNT),
        default=default_worker_count(),
        help=f"How many processes to spend on the corpus: one per core, up to {default_worker_count()} here.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Afterwards, remove the modules whose files are gone and the samples no module holds; "
            "hand annotations stay for `annotations relink`."
        ),
    )
    return parser.parse_args(argv)
