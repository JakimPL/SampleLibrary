from __future__ import annotations

import argparse
import logging
import sys

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from sampleextract.files.prune import prune_gone_sample_files
from sampleextract.files.scan import SampleFileScanOutcome, scan_sample_directories
from sampleextract.parallel.cli import add_workers_argument, raise_worker_errors
from sampleextract.prune import PruneRefused

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Scan every configured sample directory once, report it, and prune when asked.

    Raises:
        SystemExit: a prune was asked for and refused.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    config.library_root.mkdir(parents=True, exist_ok=True)
    if not config.sample_directories:
        _logger.warning("No sample_directories are configured, so there is nothing to scan.")

    outcome = scan_sample_directories(config, workers=arguments.workers)
    _report(outcome)
    raise_worker_errors(outcome.worker_errors)
    if arguments.prune:
        _prune(config, outcome)


def _report(outcome: SampleFileScanOutcome) -> None:
    """Say what the scan did, then name every directory and file it could not take in.

    A missing directory and a file that fails describe the collection, so they go out as warnings
    and the scan still ends a success: what did land is cataloged, and the passes that follow run on it.
    """
    summary = outcome.summary
    _logger.info(
        "Discovered %d sample files: %d cataloged, %d unchanged, %d shorter than minimum_sample_frames, %d failed.",
        summary.discovered,
        summary.cataloged,
        summary.unchanged,
        summary.too_short,
        len(summary.failures),
    )
    for directory in outcome.discovery.missing_directories:
        _logger.warning("The sample directory %s is not there; its cataloged files stay as they are.", directory)
    for folder in outcome.discovery.unreadable_directories:
        _logger.warning("Could not list %s.", folder)
    for failure in summary.failures:
        _logger.warning("Could not %s %s: %s", failure.stage.value, failure.path, failure.reason)


def _prune(config: LibraryConfig, outcome: SampleFileScanOutcome) -> None:
    with open_catalog_connection(config.catalog_url()) as connection:
        try:
            summary = prune_gone_sample_files(config, connection, outcome)
        except PruneRefused as error:
            _logger.error("Pruned nothing: %s.", error)
            sys.exit(ExitStatus.REFUSED)

    _logger.info(
        "Pruned %d sample file(s) no longer in the collection, %d sample(s) nothing else holds, "
        "and %d stored object(s).",
        summary.sample_files_removed,
        summary.samples_removed,
        summary.objects_removed,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Catalog the audio files in the configured sample directories.")
    add_workers_argument(parser, work="the sample files")
    parser.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Afterwards, remove the files that are gone, excluded or outside every configured directory, "
            "and the samples nothing else holds; hand annotations stay for `annotations relink`."
        ),
    )
    return parser.parse_args(argv)
