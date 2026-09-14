from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.hashing import file_sha256
from samplecore.models.sample_file import FileFingerprint
from samplecore.storage.atomic import copy_atomically, write_bytes_atomically
from samplemorph.model_paths import restorer_path
from samplemorph.model_store import model_path
from samplemorph.published import (
    PublishedModel,
    PublishedModels,
    published_codec_path,
    published_record_path,
    published_restorer_path,
)

COMMAND_NAME: Final[str] = "publish"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Make a stored codec and restorer the ones the renderer loads by default."
    )
    parser.add_argument("--model", type=str, required=True, help="The stored codec to publish, by name.")
    parser.add_argument("--restorer", type=str, required=True, help="The stored restorer to publish, by name.")


def run(config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Copy both models to the names the renderer loads, then record what was published.

    Each copy lands whole, and the record is written last, so a record naming both models stands
    only once both copies do.

    Raises:
        SystemExit: a named model is not stored.
    """
    codec = model_path(config.library_root, name=arguments.model)
    restorer = restorer_path(config.library_root, name=arguments.restorer)
    missing = [path for path in (codec, restorer) if not path.is_file()]
    if missing:
        _logger.error("Published nothing: %s is not stored.", missing[0])
        sys.exit(ExitStatus.REFUSED)

    record = PublishedModels(
        codec=_published(codec, published_codec_path(config.library_root)),
        restorer=_published(restorer, published_restorer_path(config.library_root)),
        published_at=datetime.now(UTC),
    )
    write_bytes_atomically(published_record_path(config.library_root), record.model_dump_json().encode("utf-8"))
    _logger.info("Published %s and %s as the models the renderer loads.", arguments.model, arguments.restorer)


def _published(source: Path, destination: Path) -> PublishedModel:
    copy_atomically(source, destination)
    return PublishedModel(
        source=source.name,
        content=file_sha256(destination),
        fingerprint=FileFingerprint.of(destination.stat()),
    )
