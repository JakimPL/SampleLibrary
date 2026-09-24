from __future__ import annotations

from pathlib import Path
from typing import Final

import tomlkit
from pydantic import BaseModel
from tomlkit.items import Table

from samplecore.config import LIBRARY_TABLE, LibraryConfig, parse_config
from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_bytes_atomically

MODULE_SOURCE_DIRECTORY_KEY: Final[str] = "module_source_directory"
LIBRARY_ROOT_KEY: Final[str] = "library_root"
SAMPLE_DIRECTORIES_KEY: Final[str] = "sample_directories"
SAMPLE_EXCLUSIONS_KEY: Final[str] = "sample_exclusions"


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


def write_library_sources(path: Path, sources: LibrarySources) -> LibraryConfig:
    """Put the chosen sources into the config file at ``path``, keeping every other setting and comment it holds.

    The new content is validated the way `load_config` reads it before anything is written, and the
    file is then replaced whole, so the configuration returned is the one every later command reads.

    Raises:
        ConfigurationError: the sources, together with the rest of the file, fail validation; the
            file then stays as it was.
    """
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if path.is_file() else tomlkit.document()
    library = document.get(LIBRARY_TABLE)
    if not isinstance(library, Table):
        library = tomlkit.table()
        document[LIBRARY_TABLE] = library
    _set_sources(library, sources)
    content = tomlkit.dumps(document)
    config = parse_config(content, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomically(path, content.encode("utf-8"))
    return config


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
