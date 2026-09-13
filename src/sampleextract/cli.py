from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli, integer_at_least
from samplecore.models.scalars import MINIMUM_WORKER_COUNT
from sampleextract.parallel.supervisor import default_worker_count, extract_corpus
from sampleextract.run import ExtractionSummary

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one extraction pass over the configured source directory and report it."""
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    _report(extract_corpus(config, workers=arguments.workers))


def _report(summary: ExtractionSummary) -> None:
    """Say what the pass did, then name every file it could not read.

    An unreadable file describes the collection, so it goes out as a warning and the pass still
    ends a success: what did land is cataloged, and the stages that follow extraction run on it.
    """
    _logger.info(
        "Discovered %d modules: %d ingested, %d already known, %d ingested by another worker, %d unreadable.",
        summary.discovered,
        len(summary.ingested),
        summary.skipped_existing,
        summary.ingested_elsewhere,
        len(summary.failures),
    )
    for failure in summary.failures:
        _logger.warning("Could not read %s: %s", failure.path, failure.reason)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Catalog every module under the configured source directory."
    )
    parser.add_argument(
        "--workers",
        type=integer_at_least(MINIMUM_WORKER_COUNT),
        default=default_worker_count(),
        help=(
            "How many processes to spend on the corpus. Defaults to one per core, up to a ceiling "
            "this machine's memory carries comfortably."
        ),
    )
    return parser.parse_args(argv)
