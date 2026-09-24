from __future__ import annotations

import argparse
import logging
from typing import Final

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplecore.storage.atomic import copy_atomically
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import pretrained_descriptor

COMMAND_NAME: Final[str] = "adopt"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Store the descriptor bundled with this installation in the library."
    )
    parser.add_argument("--descriptor", type=str, required=True, help="The name to store the descriptor under.")


def run(config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Copy the bundled descriptor into the library's models, under the name the pipeline gives it.

    Raises:
        PretrainedDescriptorMissingError: this installation carries no bundled descriptor.
    """
    bundled = pretrained_descriptor()
    target = descriptor_path(config.library_root, name=arguments.descriptor)
    copy_atomically(bundled.model, target)
    _logger.info("Stored the pretrained descriptor as %s.", target)
