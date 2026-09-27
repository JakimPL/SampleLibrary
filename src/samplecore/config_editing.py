from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import tomlkit
from pydantic import BaseModel
from tomlkit import TOMLDocument
from tomlkit.items import Table

from samplecore.config import LIBRARY_TABLE, SERVER_TABLE, LibraryConfig, home_exposure, parse_config
from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_bytes_atomically

MODULE_SOURCE_DIRECTORY_KEY: Final[str] = "module_source_directory"
LIBRARY_ROOT_KEY: Final[str] = "library_root"
SAMPLE_DIRECTORIES_KEY: Final[str] = "sample_directories"
SAMPLE_EXCLUSIONS_KEY: Final[str] = "sample_exclusions"
BUILD_CLOUD_KEY: Final[str] = "build_cloud"
EXPOSURE_KEY: Final[str] = "exposure"


class LibrarySources(BaseModel):
    """What a person chooses for their library: where it lives, and the folders it reads modules and samples from.

    The application writes these into the config file for a person who never opens it, and reads
    them back to show what the library holds.
    """

    model_config = FROZEN

    library_root: Path
    module_source_directory: Path | None
    sample_directories: tuple[Path, ...]
    sample_exclusions: tuple[str, ...]

    @classmethod
    def of(cls, config: LibraryConfig) -> LibrarySources:
        return cls(
            library_root=config.library_root,
            module_source_directory=config.module_source_directory,
            sample_directories=config.sample_directories,
            sample_exclusions=config.sample_exclusions,
        )


class LibraryOptions(BaseModel):
    """How the application builds and serves a person's library.

    ``build_cloud`` says whether its builds go on past the catalog to the cloud, and
    ``open_to_network`` whether the devices on the home network may open the library too, to look.
    """

    model_config = FROZEN

    build_cloud: bool
    open_to_network: bool

    @classmethod
    def of(cls, config: LibraryConfig) -> LibraryOptions:
        return cls(build_cloud=config.build_cloud, open_to_network=config.server.answers_the_home_network)


def write_library_sources(path: Path, sources: LibrarySources) -> LibraryConfig:
    """Put the chosen sources into the config file at ``path``, keeping every other setting and comment it holds.

    The new content is validated the way `load_config` reads it before anything is written, and the
    file is then replaced whole, so the configuration returned is the one every later command reads.

    Raises:
        ConfigurationError: the sources, together with the rest of the file, fail validation; the
            file then stays as it was.
    """
    return _rewrite(path, lambda document: _set_sources(_table_of(document, LIBRARY_TABLE), sources))


def write_library_options(path: Path, options: LibraryOptions) -> LibraryConfig:
    """Put the chosen build options into the config file at ``path``, keeping every other setting and comment it holds.

    Raises:
        ConfigurationError: the file, with the options in it, fails validation; it then stays as it was.
    """
    return _rewrite(path, lambda document: _set_options(document, options))


def _rewrite(path: Path, change: Callable[[TOMLDocument], None]) -> LibraryConfig:
    """Apply ``change`` to the config file, validating the whole file before it replaces the old one.

    A file the application creates says whom the library is served to, this computer alone, so a
    person opening it finds the setting beside the others.

    Raises:
        ConfigurationError: the changed file fails validation; the file then stays as it was.
    """
    if path.is_file():
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        document = tomlkit.document()
        _table_of(document, SERVER_TABLE)[EXPOSURE_KEY] = home_exposure(answers_the_home_network=False)
    change(document)
    content = tomlkit.dumps(document)
    config = parse_config(content, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomically(path, content.encode("utf-8"))
    return config


def _table_of(document: TOMLDocument, name: str) -> Table:
    """The document's table of this name, added where the file has none."""
    table = document.get(name)
    if not isinstance(table, Table):
        table = tomlkit.table()
        document[name] = table
    return table


def _set_options(document: TOMLDocument, options: LibraryOptions) -> None:
    _table_of(document, LIBRARY_TABLE)[BUILD_CLOUD_KEY] = options.build_cloud
    _table_of(document, SERVER_TABLE)[EXPOSURE_KEY] = home_exposure(answers_the_home_network=options.open_to_network)


def _set_sources(library: Table, sources: LibrarySources) -> None:
    library[LIBRARY_ROOT_KEY] = sources.library_root.as_posix()
    _set_or_remove(
        library,
        MODULE_SOURCE_DIRECTORY_KEY,
        sources.module_source_directory.as_posix() if sources.module_source_directory is not None else None,
    )
    _set_or_remove(
        library,
        SAMPLE_DIRECTORIES_KEY,
        [directory.as_posix() for directory in sources.sample_directories] or None,
    )
    _set_or_remove(library, SAMPLE_EXCLUSIONS_KEY, list(sources.sample_exclusions) or None)


def _set_or_remove(library: Table, key: str, value: str | list[str] | None) -> None:
    if value is None:
        library.pop(key, None)
        return
    library[key] = value
