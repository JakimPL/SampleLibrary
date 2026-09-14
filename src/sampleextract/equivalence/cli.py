from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli, open_catalog_audio, positive_integer
from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository
from samplecore.storage.sample_audio import readable_membership_digest
from sampleextract.equivalence.detect import detect_equivalences

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run one equivalence-detection pass over the catalog and report the result.

    A pass over the whole catalog records the samples it could read, so a later pass finding the same
    readable samples ends at once, its relations standing as they are; `--force` compares them again,
    and a pass over the first `--limit` samples leaves no record.
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    with open_catalog_audio(config) as (connection, audio):
        passes = PostgresPassCompletionRepository(connection)
        readable = readable_membership_digest(connection)
        if arguments.limit is None and not arguments.force and passes.finished_over(PassKind.EQUIVALENCE, readable):
            _logger.info(
                "The samples that can be read are the ones the last complete pass compared, so there is nothing to detect."
            )
            return
        with start_batch(connection):
            passes.forget(PassKind.EQUIVALENCE)
        summary = detect_equivalences(connection, audio, sample_limit=arguments.limit)
        after = readable_membership_digest(connection)
        if arguments.limit is None and after == readable:
            with start_batch(connection):
                passes.record(
                    PassCompletion(kind=PassKind.EQUIVALENCE, digest=readable, completed_at=datetime.now(UTC))
                )

    _logger.info(
        "Considered %d samples (%d silent, %d with no file to read now, %d pairs left for a later pass), "
        "scored %d gain and %d resampled candidates: "
        "%d bit-depth variants, %d amplification variants, %d resampled variants.",
        summary.samples_considered,
        summary.silent_samples,
        summary.unavailable_samples,
        summary.unavailable_pairs,
        summary.gain_candidates,
        summary.resampled_candidates,
        summary.bit_depth_relations,
        summary.amplification_relations,
        summary.resampled_relations,
    )


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog, description="Detect bit-depth, amplification and resampled variants among the cataloged samples."
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        default=None,
        help="Consider only the first N cataloged samples, for a quick run over a small slice.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compare every sample even when the readable samples are the ones the last complete pass compared.",
    )
    return parser.parse_args(argv)
