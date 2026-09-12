from __future__ import annotations

import argparse
from pathlib import Path

import torch

from samplemorph.registries import DEFAULT_VOCODER_NAME, RESTORED_VOCODER_NAME, VOCODER_REGISTRY
from samplemorph.training.run_settings import DEFAULT_ACCELERATOR
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME, load_restorer, restorer_path


def add_vocoder_arguments(parser: argparse.ArgumentParser) -> None:
    """The flags every command that makes a grid audible shares, declared once so each reads the same."""
    parser.add_argument(
        "--vocoder",
        choices=sorted({*VOCODER_REGISTRY, RESTORED_VOCODER_NAME}),
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
        "--device", type=str, default=DEFAULT_ACCELERATOR, help="Which device the fitted models run on."
    )


def vocoder_from(arguments: argparse.Namespace, *, library_root: Path) -> Vocoder:
    """Build the vocoder the shared flags name, loading a fitted model when the vocoder reads one.

    Raises:
        FileNotFoundError: a vocoder that reads a model was asked for and none is stored under that name.
    """
    device = torch.device(arguments.device)
    match arguments.vocoder:
        case name if name == RESTORED_VOCODER_NAME:
            return load_restorer(restorer_path(library_root, name=arguments.restorer), device=device)
        case name:
            return VOCODER_REGISTRY[name]()
