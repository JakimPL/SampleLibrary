from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Final

import torch
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.commands.fit import DEFAULT_MODEL_NAME
from samplemorph.model_store import load_named_model
from samplemorph.pipeline import MorphRoute, encode_sample, listening_set_manifest, render_listening_set
from samplemorph.registries import (
    DEFAULT_MORPHER_NAME,
    DEFAULT_VOCODER_NAME,
    LEARNED_VOCODER_NAME,
    MORPHER_REGISTRY,
    RESTORED_VOCODER_NAME,
    VOCODER_REGISTRY,
    canonicalizer_for_geometry,
)
from samplemorph.training.run_settings import DEFAULT_ACCELERATOR
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.learned import DEFAULT_PHASE_MODEL_NAME, load_phase_model, phase_model_path
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME, load_restorer, restorer_path

COMMAND_NAME: Final[str] = "render"
MANIFEST_NAME: Final[str] = "manifest.json"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(COMMAND_NAME, help="Render a listening set between two samples.")
    parser.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    parser.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    parser.add_argument("--output", type=str, required=True, help="The directory to write the audio into.")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="Which stored model to render through.")
    parser.add_argument(
        "--vocoder",
        choices=sorted({*VOCODER_REGISTRY, LEARNED_VOCODER_NAME, RESTORED_VOCODER_NAME}),
        default=DEFAULT_VOCODER_NAME,
        help="Which vocoder makes a magnitude spectrogram audible.",
    )
    parser.add_argument(
        "--restorer",
        type=str,
        default=DEFAULT_RESTORER_NAME,
        help="Which stored restorer the restored vocoder reads through.",
    )
    parser.add_argument(
        "--phase-model",
        type=str,
        default=DEFAULT_PHASE_MODEL_NAME,
        help="Which stored phase model the learned vocoder reads.",
    )
    parser.add_argument(
        "--device", type=str, default=DEFAULT_ACCELERATOR, help="Which device the learned models run on."
    )
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
            vocoder=_vocoder_for(config, arguments),
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


def _require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        ValueError: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise ValueError(f"the catalog holds no sample {sample_hash}")

    return sample


def _vocoder_for(config: LibraryConfig, arguments: argparse.Namespace) -> Vocoder:
    """Build the vocoder a render was asked for, loading a fitted model when the vocoder reads one.

    Raises:
        FileNotFoundError: a vocoder that reads a model was asked for and none is stored under that name.
    """
    device = torch.device(arguments.device)
    match arguments.vocoder:
        case name if name == RESTORED_VOCODER_NAME:
            return load_restorer(restorer_path(config.library_root, name=arguments.restorer), device=device)
        case name if name == LEARNED_VOCODER_NAME:
            return load_phase_model(phase_model_path(config.library_root, name=arguments.phase_model), device=device)
        case name:
            return VOCODER_REGISTRY[name]()
