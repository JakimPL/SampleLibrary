from __future__ import annotations

import argparse
import logging
import sys
from typing import Final

import numpy as np
from sqlalchemy import Connection

from samplecore.cli_support import positive_integer
from samplecore.config import LibraryConfig
from samplecore.storage import audio_store
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.commands.draws import add_canonicalizer_argument, canonicalizer_from, draw_probe_samples
from samplemorph.measurement.corpus import DEFAULT_PROBE_FRAME_CEILING, DEFAULT_PROBE_FRAME_FLOOR
from samplemorph.model_store import (
    DEFAULT_MODEL_NAME,
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    model_path,
    save_model,
)
from samplemorph.registries import RENDERABLE_CANONICALIZER_NAMES
from samplemorph.training.principal_components import DEFAULT_LATENT_SIZE, PrincipalComponentTrainer, stack_grids
from samplemorph.training.run_settings import DEFAULT_RANDOM_SEED

COMMAND_NAME: Final[str] = "fit"
DEFAULT_FIT_SAMPLE_COUNT: Final[int] = 4_000

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Fit a codec over a draw of the library.")
    add_canonicalizer_argument(
        parser, help_text="Which frequency axis to canonicalize onto.", names=RENDERABLE_CANONICALIZER_NAMES
    )
    parser.add_argument(
        "--latent-size", type=positive_integer, default=DEFAULT_LATENT_SIZE, help="How many components the codec keeps."
    )
    parser.add_argument(
        "--samples", type=positive_integer, default=DEFAULT_FIT_SAMPLE_COUNT, help="How many samples to fit over."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the fit use.")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="The name to store the model under.")


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Fit a linear codec over a draw of the library and write it under the library root.

    The grids are laid into one single-precision matrix as each sample is canonicalized, which
    holds a fit over the default draw to a few gigabytes.

    Raises:
        SystemExit: the library holds no sample within the probe frame bounds, or fewer than the
            codec's components, after naming the `--latent-size` that fits.
    """
    canonicalizer = canonicalizer_from(arguments)
    samples = draw_probe_samples(connection, count=arguments.samples, random_seed=arguments.seed)
    if not samples:
        _logger.error(
            "No sample lies between %d and %d frames, so there is nothing to fit a codec over.",
            DEFAULT_PROBE_FRAME_FLOOR,
            DEFAULT_PROBE_FRAME_CEILING,
        )
        sys.exit(1)
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

    geometry = canonicalizer.geometry
    bands, columns = geometry.grid_shape
    _logger.info(
        "Canonicalizing %d samples on the %s axis into a %.1f GB matrix...",
        len(samples),
        arguments.canonicalizer,
        len(samples) * bands * columns * np.dtype(np.float32).itemsize / 1e9,
    )
    grids = stack_grids(
        (
            canonicalizer.canonicalize(prepare_mono(audio_store.read(config.library_root, sample).pcm))
            for sample in samples
        ),
        count=len(samples),
        geometry=geometry,
    )
    trainer = PrincipalComponentTrainer(geometry, latent_size=arguments.latent_size, random_seed=arguments.seed)
    codec = trainer.fit(grids)
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer=arguments.canonicalizer,
        geometry=geometry,
        latent_size=codec.latent_size,
        fitted_sample_count=len(samples),
        random_seed=arguments.seed,
        explained_variance=codec.explained_variance,
    )
    path = model_path(config.library_root, name=arguments.model)
    save_model(path, MorphModel(description=description, codec=codec))

    _logger.info(
        "Fitted %d components over %d samples, holding %.1f%% of their variance. Wrote %s.",
        codec.latent_size,
        len(samples),
        100.0 * codec.explained_variance,
        path,
    )
