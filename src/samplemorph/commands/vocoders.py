from __future__ import annotations

import argparse
from pathlib import Path

from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.selection import vocoder_named


def vocoder_from(arguments: argparse.Namespace, *, library_root: Path) -> Vocoder:
    """Build the vocoder the shared flags name, loading a fitted model when the vocoder reads one.

    Raises:
        FileNotFoundError: a vocoder that reads a model was asked for and none is stored under that name.
    """
    return vocoder_named(
        arguments.vocoder, library_root=library_root, restorer_name=arguments.restorer, device=arguments.device
    )
