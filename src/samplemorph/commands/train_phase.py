from __future__ import annotations

import argparse
import logging
from typing import Final

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.commands.draws import add_canonicalizer_argument, draw_probe_samples
from samplemorph.commands.run_arguments import add_run_arguments, report_outcome, run_settings_from
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.phase_dataset import DEFAULT_CROP_FRAMES
from samplemorph.training.settings import PhaseTrainingSettings
from samplemorph.vocoders.learned import DEFAULT_PHASE_MODEL_NAME
from samplemorph.vocoders.phase_model import DEFAULT_CHANNELS

COMMAND_NAME: Final[str] = "train-phase"
PHASE_EXPERIMENT_NAME: Final[str] = "phase-vocoder"
DEFAULT_TRAIN_SAMPLE_COUNT: Final[int] = 20_000

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Teach a phase model the phase this pipeline's magnitudes carry.")
    add_canonicalizer_argument(parser, help_text="Which frequency axis the magnitudes are produced on.")
    parser.add_argument("--samples", type=int, default=DEFAULT_TRAIN_SAMPLE_COUNT, help="How many samples to train on.")
    parser.add_argument(
        "--channels", type=int, default=DEFAULT_CHANNELS, help="How much capacity the network spends per layer."
    )
    parser.add_argument(
        "--crop", type=int, default=DEFAULT_CROP_FRAMES, help="How many analysis frames one training crop spans."
    )
    parser.add_argument(
        "--phase-model", type=str, default=DEFAULT_PHASE_MODEL_NAME, help="The name to store the phase model under."
    )
    add_run_arguments(parser)


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Teach a phase model on the magnitudes this pipeline's own canonicalizer produces."""
    # The trainer and the run store are imported here, so parsing arguments and the commands that
    # train nothing stay clear of them.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.phase_data import PhaseCorpus
    from samplemorph.training.phase_run import run_phase_training
    from samplemorph.training.runs import RunPlacement

    canonicalizer = CANONICALIZER_REGISTRY[arguments.canonicalizer]()
    samples = draw_probe_samples(connection, count=arguments.samples, random_seed=arguments.seed)
    corpus = PhaseCorpus(
        samples=samples,
        library_root=config.library_root,
        canonicalizer=canonicalizer,
        canonicalizer_name=arguments.canonicalizer,
    )
    settings = PhaseTrainingSettings(
        run=run_settings_from(arguments), channels=arguments.channels, crop_frames=arguments.crop
    )
    _logger.info("Training over %d samples on the %s axis.", len(samples), arguments.canonicalizer)
    with open_run(
        config.library_root,
        recorded=not arguments.no_tracking,
        experiment_name=PHASE_EXPERIMENT_NAME,
        run_name=arguments.phase_model,
    ) as tracker:
        outcome = run_phase_training(
            corpus,
            settings=settings,
            placement=RunPlacement(
                library_root=config.library_root,
                model_name=arguments.phase_model,
                tracker=tracker,
                resume=arguments.resume,
            ),
        )

    report_outcome(outcome)
