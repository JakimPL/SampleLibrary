from __future__ import annotations

import argparse
import logging
import sys
from typing import Final

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.commands.draws import add_canonicalizer_argument, canonicalizer_from, draw_probe_samples
from samplemorph.measurement.corpus import DEFAULT_PROBE_FRAME_CEILING, DEFAULT_PROBE_FRAME_FLOOR, read_probe_samples
from samplemorph.model_store import (
    DEFAULT_MODEL_NAME,
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    model_path,
    save_model,
)
from samplemorph.training.principal_components import DEFAULT_LATENT_SIZE, PrincipalComponentTrainer
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED

COMMAND_NAME: Final[str] = "fit"
DEFAULT_FIT_SAMPLE_COUNT: Final[int] = 4_000

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Fit a codec over a draw of the library.")
    add_canonicalizer_argument(parser, help_text="Which frequency axis to canonicalize onto.")
    parser.add_argument(
        "--latent-size", type=int, default=DEFAULT_LATENT_SIZE, help="How many components the codec keeps."
    )
    parser.add_argument("--samples", type=int, default=DEFAULT_FIT_SAMPLE_COUNT, help="How many samples to fit over.")
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the fit use.")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="The name to store the model under.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Fit a linear codec over a draw of the library and write it under the library root.

    Raises:
        SystemExit: the library holds fewer samples within the probe frame bounds than the codec's
            components, after naming the `--latent-size` that fits.
    """
    canonicalizer = canonicalizer_from(arguments)
    samples = draw_probe_samples(connection, count=arguments.samples, random_seed=arguments.seed)
    if len(samples) < arguments.latent_size:
        _logger.error(
            "%d samples lie between %d and %d frames, fewer than the %d components the codec keeps. "
            "Pass --latent-size %d or less.",
            len(samples),
            DEFAULT_PROBE_FRAME_FLOOR,
            DEFAULT_PROBE_FRAME_CEILING,
            arguments.latent_size,
            len(samples),
        )
        sys.exit(1)
    _logger.info("Canonicalizing %d samples on the %s axis...", len(samples), arguments.canonicalizer)
    images = [canonicalizer.canonicalize(probe.mono) for probe in read_probe_samples(config.library_root, samples)]

    trainer = PrincipalComponentTrainer(
        canonicalizer.geometry, latent_size=arguments.latent_size, random_seed=arguments.seed
    )
    codec = trainer.fit(images)
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer=arguments.canonicalizer,
        geometry=canonicalizer.geometry,
        latent_size=codec.latent_size,
        fitted_sample_count=len(images),
        random_seed=arguments.seed,
        explained_variance=codec.explained_variance,
    )
    path = model_path(config.library_root, name=arguments.model)
    save_model(path, MorphModel(description=description, codec=codec))

    _logger.info(
        "Fitted %d components over %d samples, holding %.1f%% of their variance. Wrote %s.",
        codec.latent_size,
        len(images),
        100.0 * codec.explained_variance,
        path,
    )
