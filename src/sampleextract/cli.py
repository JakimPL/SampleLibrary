from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import bootstrap_cli
from samplecore.models.scalars import MINIMUM_WORKER_COUNT, WorkerCount
from sampleextract.parallel.supervisor import default_worker_count, extract_corpus
from sampleextract.run import ExtractionSummary

_logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run one extraction pass over the configured source directory and report it."""
    arguments = _parse_arguments(argv)
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


def _worker_count_argument(value: str) -> WorkerCount:
    """Read the ``--workers`` value, reporting a bad one the way argparse reports its own.

    Raises:
        argparse.ArgumentTypeError: the value is not a whole number, or names fewer processes than
            a run can be spent on.
    """
    try:
        workers = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"a worker count reads as a whole number, not {value!r}") from error

    if workers < MINIMUM_WORKER_COUNT:
        raise argparse.ArgumentTypeError(f"a run spends at least {MINIMUM_WORKER_COUNT} process, not {workers}")

    return workers


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract every module under the configured source directory.")
    parser.add_argument(
        "--workers",
        type=_worker_count_argument,
        default=default_worker_count(),
        help=(
            "How many processes to spend on the corpus. Defaults to one per core, up to a ceiling "
            "this machine's memory carries comfortably."
        ),
    )
    return parser.parse_args(argv)
