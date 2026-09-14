from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Connection

from samplecore.cli_support import positive_integer, positive_multiple_of
from samplecore.config import LibraryConfig
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.commands.draws import (
    add_canonicalizer_argument,
    canonicalizer_from,
    draw_probe_samples,
    readable_samples,
)
from samplemorph.commands.run_arguments import add_run_arguments, run_settings_from, train_and_report
from samplemorph.registries import RENDERABLE_CANONICALIZER_NAMES
from samplemorph.training.settings import DEFAULT_CROP_FRAMES, AnalysisTrainingSettings

if TYPE_CHECKING:
    from samplemorph.training.analysis_data import AnalysisCorpus
    from samplemorph.training.run_paths import RunFamily
    from samplemorph.training.runs import RunPlacement, TrainingOutcome

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisTrainingFlags:
    """What one family's training command says for itself: its axis wording, its defaults, and the flag naming its model.

    A `sample_count` of `None` trains on every sample the catalog holds, which is what a model of
    this library's own sounds is taught from; a count draws that many reproducibly within the
    probe bounds. `channel_step` is the count every layer's channels divide into, the groups its
    normalization reads.
    """

    axis_help: str
    sample_count: int | None
    channels: int
    channel_step: int
    model_flag: str
    model_name: str


@dataclass(frozen=True)
class AnalysisTrainer:
    """One family's trainer as a command drives it: the experiment it records under, the model name, and the run itself."""

    experiment_name: str
    family: RunFamily
    model_name: str
    train: Callable[[AnalysisCorpus, AnalysisTrainingSettings, RunPlacement], TrainingOutcome]


def add_analysis_training_arguments(parser: argparse.ArgumentParser, flags: AnalysisTrainingFlags) -> None:
    """The flags every trainer taught on the pipeline's own magnitudes shares, declared once so each reads the same."""
    add_canonicalizer_argument(parser, help_text=flags.axis_help, names=RENDERABLE_CANONICALIZER_NAMES)
    parser.add_argument(
        "--samples",
        type=positive_integer,
        default=flags.sample_count,
        help="How many samples to train on; every sample the catalog holds when left out.",
    )
    parser.add_argument(
        "--channels",
        type=positive_multiple_of(flags.channel_step),
        default=flags.channels,
        help=f"How much capacity the network spends per layer, in steps of {flags.channel_step}.",
    )
    parser.add_argument(
        "--crop",
        type=positive_integer,
        default=DEFAULT_CROP_FRAMES,
        help="How many analysis frames one training crop spans.",
    )
    parser.add_argument(flags.model_flag, type=str, default=flags.model_name, help="The name to store the model under.")
    add_run_arguments(parser)


def train_on_analysis_corpus(
    connection: Connection, config: LibraryConfig, arguments: argparse.Namespace, trainer: AnalysisTrainer
) -> None:
    """Draw the corpus and settings the shared flags name, open the run, and hand all three to the family's trainer."""
    # The run store is imported here, so parsing arguments and the commands that train nothing
    # stay clear of it.
    # pylint: disable=import-outside-toplevel
    from samplecore.tracking.session import open_run
    from samplemorph.training.analysis_data import AnalysisCorpus
    from samplemorph.training.runs import RunPlacement, check_resume_point

    audio = SampleAudio.from_catalog(connection, config.library_root)
    samples = readable_samples(
        (
            PostgresSampleRepository(connection).list_all()
            if arguments.samples is None
            else draw_probe_samples(connection, count=arguments.samples, random_seed=arguments.seed)
        ),
        audio,
    )
    corpus = AnalysisCorpus(
        samples=samples,
        audio=audio,
        canonicalizer=canonicalizer_from(arguments),
        canonicalizer_name=arguments.canonicalizer,
    )
    settings = AnalysisTrainingSettings(
        channels=arguments.channels, run=run_settings_from(arguments), crop_frames=arguments.crop
    )

    def train() -> TrainingOutcome:
        check_resume_point(config.library_root, family=trainer.family, name=trainer.model_name, resume=arguments.resume)
        _logger.info("Training over %d samples on the %s axis.", len(samples), arguments.canonicalizer)
        with open_run(
            config.library_root,
            recorded=not arguments.no_tracking,
            experiment_name=trainer.experiment_name,
            run_name=trainer.model_name,
        ) as tracker:
            placement = RunPlacement(
                library_root=config.library_root,
                family=trainer.family,
                model_name=trainer.model_name,
                tracker=tracker,
                resume=arguments.resume,
            )
            return trainer.train(corpus, settings, placement)

    train_and_report(train)
