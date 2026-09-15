from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import ending_in_one_line
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.listening.candidates import NoScoringShown
from samplemorph.listening.drawing import draw_pairs
from samplemorph.listening.pairs import write_pair_set
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED

COMMAND_NAME: Final[str] = "draw-pairs"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Draw the pairs of samples a morph comparison is listened to on."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed of the draw.")
    parser.add_argument("--output", type=str, required=True, help="The JSON file to write the pairs into.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Draw the pairs from the catalog's labels and write them for `compare` to read.

    Raises:
        SystemExit: the catalog shows no label scoring, or offers no pair at all.
    """
    audio = SampleAudio.from_catalog(connection, config.library_root)
    with ending_in_one_line("Drew nothing", (NoScoringShown,)):
        pair_set = draw_pairs(connection, audio, random_seed=arguments.seed)
    if not pair_set.pairs:
        _logger.error("Drew nothing: the catalog offers no pair for any slot.")
        sys.exit(ExitStatus.REFUSED)

    output = Path(arguments.output)
    write_pair_set(output, pair_set)
    kinds = Counter(pair.kind for pair in pair_set.pairs)
    _logger.info(
        "Drew %d pairs (%s) under scoring %d into %s.",
        len(pair_set.pairs),
        ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())),
        pair_set.experiment_id,
        output,
    )
