from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

SAMPLE_HASH = "a" * 64
MODULE_HASH = "c" * 64


def test_get_cloud_returns_every_stored_coordinate(client: TestClient, connection: Connection) -> None:
    PostgresSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )

    response = client.get("/cloud")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["sample_hash"] == SAMPLE_HASH
    assert body[0]["x"] == 1.5
    assert body[0]["y"] == -2.5
    assert body[0]["category"] == "uncategorized"


def test_get_cloud_resolves_each_point_s_category_from_its_occurrence_names(
    client: TestClient, connection: Connection
) -> None:
    PostgresSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    module_repository = PostgresModuleRepository(connection)
    module = Module(
        hash=MODULE_HASH,
        id=module_repository.next_id(),
        filename="song.xm",
        tracker=TrackerFormat.XM,
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    module_repository.insert(module)
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=SAMPLE_HASH,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
            name="kick",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )

    response = client.get("/cloud")

    assert response.status_code == 200
    assert response.json()[0]["category"] == "kick"


def test_get_cloud_carries_the_rate_a_point_is_heard_at(client: TestClient, connection: Connection) -> None:
    """Clicking a point plays it, so the speed the library sounds it at travels with the point."""
    PostgresSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )
    PostgresSamplePlaybackRateRepository(connection).replace_all({SAMPLE_HASH: 16726})

    response = client.get("/cloud")

    assert response.json()[0]["playback_rate_hz"] == 16726


def test_get_cloud_on_an_empty_catalog_returns_nothing(client: TestClient) -> None:
    response = client.get("/cloud")

    assert response.status_code == 200
    assert response.json() == []


def test_get_module_cloud_returns_every_stored_coordinate(client: TestClient, connection: Connection) -> None:
    module_repository = PostgresModuleRepository(connection)
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
    PostgresModuleCloudCoordinateRepository(connection).upsert(
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
