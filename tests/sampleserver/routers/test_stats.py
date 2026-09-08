from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository


def test_get_stats_reflects_the_seeded_catalog(client: TestClient, connection: Connection) -> None:
    sample = Sample(hash="a" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    PostgresSampleRepository(connection).upsert(sample)

    response = client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 1
    assert body["total_stored_bytes"] == sample.stored_bytes


def test_get_stats_on_an_empty_catalog(client: TestClient) -> None:
    response = client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["module_count"] == 0
    assert body["sample_count"] == 0
