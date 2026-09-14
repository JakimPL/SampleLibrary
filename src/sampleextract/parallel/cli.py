from __future__ import annotations

import argparse
import logging

from samplecore.cli_support import integer_at_least
from samplecore.models.scalars import MINIMUM_WORKER_COUNT
from sampleextract.parallel.supervisor import default_worker_count

_logger = logging.getLogger(__name__)


def add_workers_argument(parser: argparse.ArgumentParser, *, work: str) -> None:
    """Give a command spread over worker processes its ``--workers`` option, naming the ``work`` it divides."""
    parser.add_argument(
        "--workers",
        type=integer_at_least(MINIMUM_WORKER_COUNT),
        default=default_worker_count(),
        help=f"How many processes to spend on {work}: one per core, up to {default_worker_count()} here.",
    )


def raise_worker_errors(worker_errors: tuple[BaseException, ...]) -> None:
    """Report every share that stopped, then raise the first error, which is what the run ends with."""
    for error in worker_errors:
        _logger.error("A worker process stopped: %s", error, exc_info=error)
    if worker_errors:
        raise worker_errors[0]
