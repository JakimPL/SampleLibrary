from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import SampleCloudCoordinate
from samplecore.models.sample import Sample
from samplecore.storage.repositories.cloud import DuckDBCloudCoordinateRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository

SAMPLE_HASH = "a" * 64


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
