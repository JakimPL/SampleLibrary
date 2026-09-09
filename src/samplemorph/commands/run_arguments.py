from __future__ import annotations

import argparse
import logging

from samplemorph.training.run_settings import (
    DEFAULT_ACCELERATOR,
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_LEARNING_RATE,
    DEFAULT_PRECISION,
    DEFAULT_RANDOM_SEED,
    DEFAULT_WORKER_COUNT,
    TRAINING_PRECISIONS,
    RunSettings,
)
from samplemorph.training.runs import TrainingOutcome

_logger = logging.getLogger(__name__)


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """The flags every training command shares, declared once so each reads the same."""
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS, help="How many passes over the training samples.")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="How many examples make up one step.")
    parser.add_argument(
        "--learning-rate", type=float, default=DEFAULT_LEARNING_RATE, help="The rate the optimizer starts at."
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKER_COUNT, help="How many processes prepare training examples."
    )
    parser.add_argument(
        "--precision",
        type=str,
        default=DEFAULT_PRECISION,
        choices=TRAINING_PRECISIONS,
        help="The arithmetic a training step is computed in.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed every draw and split uses.")
    parser.add_argument("--device", type=str, default=DEFAULT_ACCELERATOR, help="Which device to train on.")
    parser.add_argument(
        "--resume", action="store_true", help="Continue the run of this name from where it last stopped."
    )
    parser.add_argument("--no-tracking", action="store_true", help="Run without keeping a record of it.")


def run_settings_from(arguments: argparse.Namespace) -> RunSettings:
    """The shared flags read back into the settings every trainer is driven by."""
    return RunSettings(
        epochs=arguments.epochs,
        batch_size=arguments.batch,
        learning_rate=arguments.learning_rate,
        worker_count=arguments.workers,
        precision=arguments.precision,
        accelerator=arguments.device,
        random_seed=arguments.seed,
    )


def report_outcome(outcome: TrainingOutcome) -> None:
    """Say how a run ended and where its best epoch was written."""
    _logger.info(
        "Trained for %d epochs. The best epoch scored %.4f and is what %s holds.",
        outcome.epochs_completed,
        outcome.best_validation_loss,
        outcome.model_path,
    )
