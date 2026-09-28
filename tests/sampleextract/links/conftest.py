from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.hashing import compute_module_hash
from samplecore.models.module import Module
from samplecore.storage.repositories.module import PostgresModuleRepository
from sampleextract.discovery import FORMAT_LOADERS


@pytest.fixture
def collection(tmp_path: Path) -> Path:
    directory = tmp_path / "modules"
    directory.mkdir()
    return directory


def catalog_module_file(connection: Connection, collection: Path, location: str, data: bytes) -> Module:
    """Write a module file at ``location`` under the collection and catalog it under the hash of its bytes."""
    file = collection.joinpath(*location.split("/"))
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)
    repository = PostgresModuleRepository(connection)
    module = Module(
        hash=compute_module_hash(data),
        id=repository.next_id(),
        filename=file.name,
        tracker=FORMAT_LOADERS[file.suffix.lower()],
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=len(data),
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module


def write_links(path: Path, rows: tuple[tuple[str, str], ...]) -> Path:
    path.write_text("location,link\n" + "".join(f"{location},{link}\n" for location, link in rows), encoding="utf-8")
    return path
