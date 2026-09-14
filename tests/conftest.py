from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import numpy as np
import pytest
import soundfile
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from samplecore.config import ConfigurationError, load_config
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage.curation import curation_metadata
from samplecore.storage.database import connect, metadata
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository

SERVER_URL_VARIABLE: Final[str] = "SAMPLELIBRARY_TEST_DATABASE_URL"
TEST_DATABASE_NAME: Final[str] = "samplelibrary_test"
DEFAULT_SERVER_URL: Final[str] = f"postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/{TEST_DATABASE_NAME}"
VANISHED_SAMPLE_FRAMES: Final[int] = 2048
VANISHED_SAMPLE_RATE: Final[int] = 44100


@pytest.fixture(scope="session")
def _server_url() -> str:
    """The Postgres server the suite runs against, and the database on it the suite starts from.

    ``SAMPLELIBRARY_TEST_DATABASE_URL`` names it outright; otherwise the server the configuration
    names is used, under the ``samplelibrary_test`` database `just database` creates, so a library
    set up on another port is tested on that port; with no configuration to read, a local server
    on the default port. The database this URL names is only ever connected to in order to create
    and drop the per-worker databases below, so it needs to exist but stays empty. The role it
    authenticates as needs ``CREATEDB``.
    """
    named = os.environ.get(SERVER_URL_VARIABLE)
    if named:
        return named
    try:
        configured = load_config().database_url
    except ConfigurationError:
        return DEFAULT_SERVER_URL
    return make_url(configured).set(database=TEST_DATABASE_NAME).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def _database_url(_server_url: str, worker_id: str) -> Iterator[str]:
    """A database of this test worker's own, created empty for the session and dropped after it.

    Running under ``pytest -n auto`` puts every worker on the same server, where the ``connection``
    fixture's habit of emptying every table between tests would otherwise reach into whatever the
    other workers are doing at that moment. One database per worker keeps that cleanup local to the
    worker performing it. ``CREATE DATABASE``/``DROP DATABASE`` cannot run inside a transaction
    block, hence the ``AUTOCOMMIT`` isolation level.
    """
    server_url = make_url(_server_url)
    database_name = f"{server_url.database}_{worker_id}"
    admin_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as admin_connection:
        admin_connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        try:
            # str() on a URL renders its password as "***"; the yielded URL has to carry the real one.
            yield server_url.set(database=database_name).render_as_string(hide_password=False)
        finally:
            admin_connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture
def connection(_database_url: str) -> Iterator[Connection]:
    """A catalog connection to this worker's database, with an empty schema on every test.

    Emptying every table at teardown, children before the tables they reference, gives each test the same "starts from nothing" guarantee -- rolling back first discards any
    transaction a failing test left open, so the cleanup deletes themselves always run against a
    clean transaction state.

    The curation tables are named here deliberately, since they live on a metadata of their own that
    ``reset_library`` has no reach into. A test wants them cleared between cases; a real library
    wants them kept, and that difference is exactly what the separate metadata buys.
    """
    open_connection = connect(_database_url)
    try:
        yield open_connection
    finally:
        open_connection.rollback()
        for table in [*reversed(metadata.sorted_tables), *reversed(curation_metadata.sorted_tables)]:
            open_connection.execute(table.delete())
        open_connection.commit()
        open_connection.close()


@pytest.fixture
def vanished_sample_file(connection: Connection, tmp_path: Path) -> SampleFile:
    """A sample a scan found in a file of a sample directory, whose file has since been deleted.

    The catalog still holds the sample, its thumbnail and its file row, so every pass reaches it and
    none can read it: the case of a folder of samples on a drive that is no longer plugged in.
    """
    directory = tmp_path / "vanished pack"
    path = directory / "Kicks" / "Gone 01.wav"
    path.parent.mkdir(parents=True)
    soundfile.write(path, np.linspace(-0.5, 0.5, VANISHED_SAMPLE_FRAMES), VANISHED_SAMPLE_RATE, subtype="PCM_16")
    decoded = decode_sample_file(path)
    sample_file = SampleFile(
        sample_hash=decoded.sample_pcm.sample.hash,
        location=SampleFileLocation(directory=directory, relative_path="Kicks/Gone 01.wav"),
        rate=decoded.rate,
        fingerprint=FileFingerprint.of(path.stat()),
    )
    PostgresSampleRepository(connection).upsert(decoded.sample_pcm.sample)
    PostgresSampleFileRepository(connection).upsert(sample_file)
    connection.commit()
    path.unlink()
    return sample_file
