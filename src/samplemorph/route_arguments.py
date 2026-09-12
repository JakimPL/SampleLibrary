from __future__ import annotations

import argparse

from samplemorph.model_store import DEFAULT_MODEL_NAME
from samplemorph.pipeline import RouteChoice
from samplemorph.registries import (
    DEFAULT_MORPHER_NAME,
    DEFAULT_VOCODER_NAME,
    MORPHER_REGISTRY,
    RESTORED_VOCODER_NAME,
    VOCODER_REGISTRY,
)
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME


def add_model_argument(parser: argparse.ArgumentParser) -> None:
    """The flag naming the stored model a route decodes through."""
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help="Which stored model to render through.")


def add_vocoder_arguments(parser: argparse.ArgumentParser, *, device_default: str) -> None:
    """The flags every entry point that makes a grid audible shares, declared once so each reads the same.

    The device's default is the caller's to state: a training shell reaches for the card, a
    long-lived service for the processor.
    """
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
    parser.add_argument("--device", type=str, default=device_default, help="Which device the fitted models run on.")


def add_morpher_argument(parser: argparse.ArgumentParser) -> None:
    """The flag naming the route a morph takes between two latents."""
    parser.add_argument(
        "--morpher",
        choices=sorted(MORPHER_REGISTRY),
        default=DEFAULT_MORPHER_NAME,
        help="Which route the morph takes between the two latents.",
    )


def route_choice_from(arguments: argparse.Namespace) -> RouteChoice:
    """The route the model, vocoder, restorer, morpher and device flags name together."""
    return RouteChoice(
        model_name=arguments.model,
        vocoder_name=arguments.vocoder,
        restorer_name=arguments.restorer,
        morpher_name=arguments.morpher,
        device=arguments.device,
    )
