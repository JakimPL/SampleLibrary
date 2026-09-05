from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from samplecore.storage.repositories.thumbnail import DuckDBSampleThumbnailRepository

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64


def _insert_sample(connection: duckdb.DuckDBPyConnection, sample_hash: str, *, frames: int = 8) -> Sample:
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frames)
    DuckDBSampleRepository(connection).upsert(sample)
    return sample


def _insert_module(
    connection: duckdb.DuckDBPyConnection, *, filename: str = "song.xm", title: str = "a song"
) -> Module:
    repository = DuckDBModuleRepository(connection)
    module = Module(
        hash="c" * 64,
        id=repository.next_id(),
        filename=filename,
        tracker=TrackerFormat.XM,
        title=title,
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    return module


def _add_occurrence(
    connection: duckdb.DuckDBPyConnection,
    *,
    sample: Sample,
    module: Module,
    slot: int = 0,
    name: str = "lead",
    rate: int = 8363,
) -> None:
    DuckDBSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name=name,
            rate=rate,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def test_list_samples_returns_a_page(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)

    response = client.get("/samples")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["hash"] for item in body["items"]} == {first.hash, second.hash}


def test_list_samples_ranks_by_occurrence_count(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    frequent = _insert_sample(connection, SAMPLE_HASH_A)
    rare = _insert_sample(connection, SAMPLE_HASH_B)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=frequent, module=module, slot=0, name="kick")
    _add_occurrence(connection, sample=frequent, module=module, slot=1, name="kick")

    response = client.get("/samples")

    body = response.json()
    assert [item["hash"] for item in body["items"]] == [frequent.hash, rare.hash]
    assert body["items"][0]["occurrence_count"] == 2
    assert body["items"][0]["display_name"] == "kick"


def test_list_samples_resolves_the_dominant_occurrence_rate(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="kick", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="kick", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=2, name="kick", rate=22050)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["dominant_rate_hz"] == 8363


def test_list_samples_leaves_dominant_rate_null_for_a_sample_with_no_occurrences(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["dominant_rate_hz"] is None


def test_list_samples_includes_a_cached_thumbnail(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    DuckDBSampleThumbnailRepository(connection).upsert(
        SampleThumbnail(sample_hash=sample.hash, bucket_count=2, minimums=(-1.0, -0.5), maximums=(0.5, 1.0))
    )

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["thumbnail"] == [
        {"minimum": -1.0, "maximum": 0.5},
        {"minimum": -0.5, "maximum": 1.0},
    ]


def test_list_samples_leaves_thumbnail_null_when_not_yet_cached(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["thumbnail"] is None


def test_list_samples_respects_limit_and_offset(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)
    _insert_sample(connection, SAMPLE_HASH_B)

    response = client.get("/samples", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_get_sample_returns_detail_with_occurrences_and_module_context(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection, filename="song.xm", title="a song")
    _add_occurrence(connection, sample=sample, module=module, name="lead")

    response = client.get(f"/samples/{sample.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["hash"] == sample.hash
    assert body["display_name"] == "lead"
    assert len(body["occurrences"]) == 1
    occurrence = body["occurrences"][0]
    assert occurrence["properties"]["name"] == "lead"
    assert occurrence["module"] == {
        "hash": module.hash,
        "filename": "song.xm",
        "title": "a song",
        "tracker": "xm",
    }


def test_get_sample_resolves_the_dominant_occurrence_rate(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="lead", rate=22050)
    _add_occurrence(connection, sample=sample, module=module, slot=2, name="lead", rate=22050)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["dominant_rate_hz"] == 22050


def test_get_sample_resolves_a_shared_module_only_once_across_occurrences(
    client: TestClient, connection: duckdb.DuckDBPyConnection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead")
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="lead")

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert len(body["occurrences"]) == 2
    assert {occurrence["module"]["hash"] for occurrence in body["occurrences"]} == {module.hash}


def test_get_sample_reports_size_and_duration(client: TestClient, connection: duckdb.DuckDBPyConnection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A, frames=audio_store.NOMINAL_WAV_RATE)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["size_bytes"] == sample.stored_bytes
    assert body["duration_seconds"] == 1.0


def test_get_sample_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}")

    assert response.status_code == 404


def test_get_sample_audio_serves_the_stored_wav_file(
    client: TestClient, connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    sample = Sample(hash=SAMPLE_HASH_A, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
    DuckDBSampleRepository(connection).upsert(sample)
    pcm = np.zeros((4, 1), dtype=np.float64)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=pcm))

    response = client.get(f"/samples/{sample.hash}/audio")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"


def test_get_sample_audio_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}/audio")

    assert response.status_code == 404


def test_get_sample_waveform_returns_peaks(
    client: TestClient, connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    sample = Sample(hash=SAMPLE_HASH_A, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
    DuckDBSampleRepository(connection).upsert(sample)
    pcm = np.array([[0.5], [-0.5], [0.25], [-0.25]], dtype=np.float64)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=pcm))

    response = client.get(f"/samples/{sample.hash}/waveform")

    assert response.status_code == 200
    peaks = response.json()
    assert len(peaks) == 4
    assert all({"minimum", "maximum"} == set(peak) for peak in peaks)


def test_get_sample_waveform_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}/waveform")

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
