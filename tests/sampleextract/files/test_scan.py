from __future__ import annotations

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleextract.files.scan import scan_sample_directories

WORKER_COUNT = 2


def test_workers_between_them_catalog_every_sample_file_exactly_once(
    connection: Connection, files_config: LibraryConfig
) -> None:
    outcome = scan_sample_directories(files_config, workers=WORKER_COUNT)

    assert outcome.worker_errors == ()
    assert (outcome.summary.discovered, outcome.summary.cataloged) == (4, 3)
    cataloged = {sample_file.location for sample_file in PostgresSampleFileRepository(connection).list_all()}
    assert cataloged == outcome.summary.present_locations
