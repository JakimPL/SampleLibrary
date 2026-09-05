from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64


def _insert_sample(connection: duckdb.DuckDBPyConnection, sample_hash: str) -> Sample:
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    DuckDBSampleRepository(connection).upsert(sample)
    return sample


def _insert_module(connection: duckdb.DuckDBPyConnection) -> Module:
    repository = DuckDBModuleRepository(connection)
    module = Module(
        hash="c" * 64,
        id=repository.next_id(),
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
    repository.insert(module)
    return module


def test_get_sample_returns_detail_with_occurrences(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    DuckDBSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
            name="lead",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )

    response = client.get(f"/samples/{sample.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["hash"] == sample.hash
    assert len(body["occurrences"]) == 1
    assert body["occurrences"][0]["name"] == "lead"


def test_get_sample_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}")

    assert response.status_code == 404


def test_get_sample_relations_returns_the_equivalence_class(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    relation_repository = DuckDBSampleRelationRepository(connection)
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=first.hash,
            reference_hash=second.hash,
            relation_type=RelationType.BIT_DEPTH_VARIANT,
            method="bit_depth_variant/mse_v1",
            confidence=0.9,
            evidence={"rms_error": 0.001, "max_abs_error": 0.002},
            detected_at=datetime.now(UTC),
        )
    )

    response = client.get(f"/samples/{first.hash}/relations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["reference_hash"] == second.hash


def test_get_sample_relations_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}/relations")

    assert response.status_code == 404
