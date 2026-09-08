from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

_LISTED_SAMPLE_HASH = "e" * 64


def _insert_module_without_samples(connection: Connection, seed: int, *, tracker: TrackerFormat) -> Module:
    repository = PostgresModuleRepository(connection)
    module = Module(
        hash=format(seed, "064x"),
        id=repository.next_id(),
        filename="song.xm",
        tracker=tracker,
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    return module


def _insert_module(connection: Connection, seed: int, *, tracker: TrackerFormat) -> Module:
    """A module as the listing expects one: cataloged, with a sample the library actually holds."""
    module = _insert_module_without_samples(connection, seed, tracker=tracker)
    PostgresSampleRepository(connection).upsert(
        Sample(hash=_LISTED_SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=_LISTED_SAMPLE_HASH,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
            name="lead",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )
    return module


def test_list_modules_returns_a_page(client: TestClient, connection: Connection) -> None:
    first = _insert_module(connection, 1, tracker=TrackerFormat.XM)
    second = _insert_module(connection, 2, tracker=TrackerFormat.IT)

    response = client.get("/modules")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["hash"] for item in body["items"]} == {first.hash, second.hash}


def test_list_modules_leaves_out_a_module_the_library_holds_no_sample_from(
    client: TestClient, connection: Connection
) -> None:
    """A chiptune of single-cycle waveforms stays cataloged, and browsing past it is noise."""
    listed = _insert_module(connection, 1, tracker=TrackerFormat.XM)
    chiptune = _insert_module_without_samples(connection, 2, tracker=TrackerFormat.MOD)

    body = client.get("/modules").json()

    assert {item["hash"] for item in body["items"]} == {listed.hash}
    assert body["total"] == 1
    assert client.get(f"/modules/{chiptune.hash}").status_code == 200


def test_list_modules_respects_limit_and_offset(client: TestClient, connection: Connection) -> None:
    _insert_module(connection, 1, tracker=TrackerFormat.XM)
    _insert_module(connection, 2, tracker=TrackerFormat.XM)

    response = client.get("/modules", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_modules_filters_by_tracker(client: TestClient, connection: Connection) -> None:
    xm_module = _insert_module(connection, 1, tracker=TrackerFormat.XM)
    _insert_module(connection, 2, tracker=TrackerFormat.IT)

    response = client.get("/modules", params={"tracker": "xm"})

    assert response.status_code == 200
    body = response.json()
    assert [item["hash"] for item in body["items"]] == [xm_module.hash]


def test_get_module_returns_detail_with_occurrences(client: TestClient, connection: Connection) -> None:
    module = _insert_module_without_samples(connection, 1, tracker=TrackerFormat.XM)

    response = client.get(f"/modules/{module.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["hash"] == module.hash
    assert body["occurrences"] == []


def test_get_module_resolves_each_occurrence_s_sample_content_and_thumbnail(
    client: TestClient, connection: Connection, tmp_path: Path
) -> None:
    module = _insert_module_without_samples(connection, 1, tracker=TrackerFormat.XM)
    sample = Sample(hash="a" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
    PostgresSampleRepository(connection).upsert(sample)
    pcm = np.array([[0.5], [-0.5], [0.25], [-0.25]], dtype=np.float64)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=pcm))
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
            name="lead",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )

    response = client.get(f"/modules/{module.hash}")

    assert response.status_code == 200
    occurrence = response.json()["occurrences"][0]
    assert occurrence["properties"]["name"] == "lead"
    assert occurrence["sample"]["hash"] == sample.hash
    assert occurrence["sample"]["depth"] == 16
    assert occurrence["sample"]["frames"] == 4
    assert occurrence["sample"]["size_bytes"] == sample.stored_bytes
    assert occurrence["sample"]["thumbnail"] is None


def test_get_module_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/modules/{'f' * 64}")

    assert response.status_code == 404
