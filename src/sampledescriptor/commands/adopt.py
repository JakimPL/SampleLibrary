from __future__ import annotations

import argparse
import logging
from typing import Final

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import download_pretrained, pretrained_release

COMMAND_NAME: Final[str] = "adopt"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Download the published pretrained descriptor into the library."
    )
    parser.add_argument("--descriptor", type=str, required=True, help="The name to store the descriptor under.")


def run(config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Download the published descriptor into the library's models, under the name the pipeline gives it.

    Raises:
        PretrainedDescriptorMissingError: no descriptor is published for this version.
        PretrainedDownloadError: the download failed, or its bytes differ from the release.
    """
    target = descriptor_path(config.library_root, name=arguments.descriptor)
    download_pretrained(pretrained_release(), target)
    _logger.info("Stored the pretrained descriptor as %s.", target)
