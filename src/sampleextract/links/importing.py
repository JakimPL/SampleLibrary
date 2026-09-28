from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from sqlalchemy import Connection

from samplecore.hashing import compute_module_hash
from samplecore.models.module_link import ModuleLink
from samplecore.progress import tracked
from samplecore.storage.database import HASH_CHUNK_SIZE, chunks, start_batch
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.module_link import PostgresModuleLinkRepository
from sampleextract.links.file import LinkFileRefused, LinkRow, read_link_rows
from sampleextract.links.messages import CONFLICTING_LINKS

NAMED_SKIPS: Final[int] = 5
HASHING_LABEL: Final[str] = "Reading module files"


@dataclass(frozen=True)
class LinkImportSummary:
    """What one import recorded, and the locations it passed over: files it could not read, and files no module is cataloged from."""

    recorded: int
    missing: tuple[str, ...]
    uncataloged: tuple[str, ...]
    path: Path


@dataclass(frozen=True)
class _ResolvedRows:
    """The rows of a file read as modules: one link per module hash, the first location naming each, and the files not read."""

    links_by_hash: dict[str, ModuleLink]
    locations_by_hash: dict[str, str]
    missing: tuple[str, ...]


def import_links(connection: Connection, *, path: Path, source_directory: Path) -> LinkImportSummary:
    """Record the page each module the file names came from, reading each file under the collection to know the module.

    The whole file is read and checked first, so a file with a bad row changes nothing. Each row's
    file is then hashed the way extraction hashes it, which is what names the module: a copy under
    another name links the same module. A file that is missing or unreadable, and a file no
    cataloged module was read from, are passed over and counted. The links land in one
    transaction, each replacing what its module held, while every other module keeps its link.

    Raises:
        LinkFileRefused: the file cannot be read as rows of locations and links, or two of its rows
            hold one module under two links.
    """
    resolved = _resolve(read_link_rows(path), source_directory)
    hashes = sorted(resolved.links_by_hash)
    cataloged = _cataloged_hashes(connection, hashes)
    links = tuple(resolved.links_by_hash[module_hash] for module_hash in hashes if module_hash in cataloged)
    uncataloged = tuple(
        resolved.locations_by_hash[module_hash] for module_hash in hashes if module_hash not in cataloged
    )
    with start_batch(connection):
        PostgresModuleLinkRepository(connection).upsert_many(links)
    return LinkImportSummary(recorded=len(links), missing=resolved.missing, uncataloged=uncataloged, path=path)


def _resolve(rows: tuple[LinkRow, ...], source_directory: Path) -> _ResolvedRows:
    """Each row read as the module its file hashes to, in the order the rows stand.

    Raises:
        LinkFileRefused: two rows hold one module under two links.
    """
    links_by_hash: dict[str, ModuleLink] = {}
    locations_by_hash: dict[str, str] = {}
    missing: list[str] = []
    for row in tracked(rows, total=len(rows), label=HASHING_LABEL):
        file = source_directory.joinpath(*PurePosixPath(row.location).parts)
        try:
            module_hash = compute_module_hash(file.read_bytes())
        except OSError:
            missing.append(row.location)
            continue
        earlier = links_by_hash.get(module_hash)
        if earlier is not None and earlier.url != row.link:
            raise LinkFileRefused(
                CONFLICTING_LINKS.format(
                    first=locations_by_hash[module_hash], second=row.location, module_hash=module_hash
                )
            )
        links_by_hash.setdefault(module_hash, ModuleLink(module_hash=module_hash, url=row.link))
        locations_by_hash.setdefault(module_hash, row.location)
    return _ResolvedRows(links_by_hash=links_by_hash, locations_by_hash=locations_by_hash, missing=tuple(missing))


def _cataloged_hashes(connection: Connection, hashes: list[str]) -> frozenset[str]:
    """Those of ``hashes`` a module is cataloged under, looked up in chunks Postgres binds."""
    repository = PostgresModuleRepository(connection)
    cataloged: set[str] = set()
    for chunk in chunks(hashes, HASH_CHUNK_SIZE):
        cataloged.update(repository.get_many(list(chunk)))
    return frozenset(cataloged)
