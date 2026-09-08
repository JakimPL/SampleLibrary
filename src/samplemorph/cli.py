from __future__ import annotations

import argparse
import logging
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.cli_support import bootstrap_cli, open_catalog_connection
from samplecore.config import LibraryConfig
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.measurement.corpus import (
    DEFAULT_PROBE_FRAME_CEILING,
    DEFAULT_PROBE_FRAME_FLOOR,
    read_probe_samples,
)
from samplemorph.model_store import (
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    load_model,
    model_path,
    save_model,
)
from samplemorph.pipeline import MorphRoute, encode_sample, listening_set_manifest, render_listening_set
from samplemorph.registries import (
    CANONICALIZER_REGISTRY,
    DEFAULT_CANONICALIZER_NAME,
    DEFAULT_MORPHER_NAME,
    DEFAULT_VOCODER_NAME,
    MORPHER_REGISTRY,
    VOCODER_REGISTRY,
)
from samplemorph.training.principal_components import (
    DEFAULT_LATENT_SIZE,
    DEFAULT_RANDOM_SEED,
    PrincipalComponentTrainer,
)

DEFAULT_MODEL_NAME: Final[str] = "principal_components"
DEFAULT_FIT_SAMPLE_COUNT: Final[int] = 4_000
MANIFEST_NAME: Final[str] = "manifest.json"

_logger = logging.getLogger(__name__)


@unique
class MorphCommand(StrEnum):
    """The two things this pipeline does from a shell: fit a codec, and render audio through one."""

    FIT = "fit"
    RENDER = "render"


def main(argv: list[str] | None = None) -> None:
    """Fit a codec over the library, or render a listening set through one, and report the result."""
    arguments = _parse_arguments(argv)
    config = bootstrap_cli()
    with open_catalog_connection(config.database_url) as connection:
        match MorphCommand(arguments.command):
            case MorphCommand.FIT:
                _fit(connection, config, arguments)
            case MorphCommand.RENDER:
                _render(connection, config, arguments)


def _fit(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    canonicalizer = CANONICALIZER_REGISTRY[arguments.canonicalizer]()
    samples = PostgresSampleRepository(connection).sample_reproducibly(
        count=arguments.samples,
        random_seed=arguments.seed,
        frame_floor=DEFAULT_PROBE_FRAME_FLOOR,
        frame_ceiling=DEFAULT_PROBE_FRAME_CEILING,
    )
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


def _render(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    model = load_model(model_path(config.library_root, name=arguments.model))
    canonicalizer = _canonicalizer_for(model)
    codec = model.codec
    first = encode_sample(
        connection,
        config.library_root,
        _require_sample(connection, arguments.first),
        canonicalizer=canonicalizer,
        codec=codec,
    )
    second = encode_sample(
        connection,
        config.library_root,
        _require_sample(connection, arguments.second),
        canonicalizer=canonicalizer,
        codec=codec,
    )

    output_directory = Path(arguments.output)
    summary = render_listening_set(
        first,
        second,
        route=MorphRoute(
            canonicalizer=canonicalizer,
            codec=codec,
            vocoder=VOCODER_REGISTRY[arguments.vocoder](),
            morpher=MORPHER_REGISTRY[arguments.morpher](),
        ),
        output_directory=output_directory,
    )
    (output_directory / MANIFEST_NAME).write_text(listening_set_manifest(model.description, summary))

    _logger.info(
        "Wrote %d files for %s against %s, %d of them morphs, into %s.",
        len(summary.files),
        summary.first_hash[:12],
        summary.second_hash[:12],
        summary.morph_count,
        output_directory,
    )


def _canonicalizer_for(model: MorphModel) -> Canonicalizer:
    """Rebuild the frequency axis a model was fitted on.

    Raises:
        ValueError: the model names a canonicalizer this build has no entry for.
    """
    if model.description.canonicalizer not in CANONICALIZER_REGISTRY:
        raise ValueError(f"this model was fitted on the unknown {model.description.canonicalizer} axis")

    return CANONICALIZER_REGISTRY[model.description.canonicalizer]()


def _require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        ValueError: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise ValueError(f"the catalog holds no sample {sample_hash}")

    return sample


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a decodable sample codec, and render morphs through it.")
    commands = parser.add_subparsers(dest="command", required=True)

    fit = commands.add_parser(MorphCommand.FIT.value, help="Fit a codec over a draw of the library.")
    fit.add_argument(
        "--canonicalizer",
        choices=sorted(CANONICALIZER_REGISTRY),
        default=DEFAULT_CANONICALIZER_NAME,
        help="Which frequency axis to canonicalize onto.",
    )
    fit.add_argument(
        "--latent-size", type=int, default=DEFAULT_LATENT_SIZE, help="How many components the codec keeps."
    )
    fit.add_argument("--samples", type=int, default=DEFAULT_FIT_SAMPLE_COUNT, help="How many samples to fit over.")
    fit.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED, help="The seed the draw and the fit use.")
    fit.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="The name to store the model under.")

    render = commands.add_parser(MorphCommand.RENDER.value, help="Render a listening set between two samples.")
    render.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    render.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    render.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    render.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="Which stored model to render through.")
    render.add_argument(
        "--vocoder",
        choices=sorted(VOCODER_REGISTRY),
        default=DEFAULT_VOCODER_NAME,
        help="Which vocoder estimates the phase a magnitude spectrogram lost.",
    )
    render.add_argument(
        "--morpher",
        choices=sorted(MORPHER_REGISTRY),
        default=DEFAULT_MORPHER_NAME,
        help="Which route the morph takes between the two latents.",
    )
    return parser.parse_args(argv)
