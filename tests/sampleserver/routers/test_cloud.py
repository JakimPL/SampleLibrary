from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository, DuckDBModuleCloudCoordinateRepository
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository

SAMPLE_HASH = "a" * 64
MODULE_HASH = "c" * 64


def test_get_cloud_returns_every_stored_coordinate(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    DuckDBSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    DuckDBCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )

    response = client.get("/cloud")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["sample_hash"] == SAMPLE_HASH
    assert body[0]["x"] == 1.5
    assert body[0]["y"] == -2.5


def test_get_cloud_on_an_empty_catalog_returns_nothing(client: TestClient) -> None:
    response = client.get("/cloud")

    assert response.status_code == 200
    assert response.json() == []


def test_get_module_cloud_returns_every_stored_coordinate(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    module_repository = DuckDBModuleRepository(connection)
    module_repository.insert(
        Module(
            hash=MODULE_HASH,
            id=module_repository.next_id(),
            filename="song.it",
            tracker=TrackerFormat.IT,
            title="untitled",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    DuckDBModuleCloudCoordinateRepository(connection).upsert(
        ModuleCloudCoordinate(module_hash=MODULE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )

    response = client.get("/cloud/modules")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["module_hash"] == MODULE_HASH
    assert body[0]["x"] == 1.5
    assert body[0]["y"] == -2.5


def test_get_module_cloud_on_an_empty_catalog_returns_nothing(client: TestClient) -> None:
    response = client.get("/cloud/modules")

    assert response.status_code == 200
    assert response.json() == []
