from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplemorph.commands.draws import require_sample
from samplemorph.commands.fit import DEFAULT_MODEL_NAME
from samplemorph.commands.vocoders import add_vocoder_arguments, vocoder_from
from samplemorph.model_store import load_named_model
from samplemorph.pipeline import MorphRoute, encode_sample, listening_set_manifest, render_listening_set
from samplemorph.registries import DEFAULT_MORPHER_NAME, MORPHER_REGISTRY, canonicalizer_for_geometry

COMMAND_NAME: Final[str] = "render"
MANIFEST_NAME: Final[str] = "manifest.json"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Render a listening set between two samples.")
    parser.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    parser.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    parser.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="Which stored model to render through.")
    add_vocoder_arguments(parser)
    parser.add_argument(
        "--morpher",
        choices=sorted(MORPHER_REGISTRY),
        default=DEFAULT_MORPHER_NAME,
        help="Which route the morph takes between the two latents.",
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Render a listening set between two samples through a stored model."""
    model = load_named_model(config.library_root, name=arguments.model, device=arguments.device)
    canonicalizer = canonicalizer_for_geometry(model.description.geometry)
    codec = model.codec
    first = encode_sample(
        connection,
        config.library_root,
        require_sample(connection, arguments.first),
        canonicalizer=canonicalizer,
        codec=codec,
    )
    second = encode_sample(
        connection,
        config.library_root,
        require_sample(connection, arguments.second),
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
            vocoder=vocoder_from(arguments, library_root=config.library_root),
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
