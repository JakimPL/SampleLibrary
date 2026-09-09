from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.notes.pitch import Note
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.note_event import NoteEvent
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64
REFERENCE_KEY = Note(60)
OCTAVE_ABOVE_REFERENCE_KEY = Note(72)


def _insert_sample(connection: Connection, sample_hash: str, *, frames: int = 8) -> Sample:
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frames)
    PostgresSampleRepository(connection).upsert(sample)
    return sample


def _insert_module(connection: Connection, *, filename: str = "song.xm", title: str = "a song") -> Module:
    repository = PostgresModuleRepository(connection)
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
    connection: Connection,
    *,
    sample: Sample,
    module: Module,
    slot: int = 0,
    name: str = "lead",
    rate: int = 8363,
) -> None:
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name=name,
            rate=rate,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def _play_note(connection: Connection, *, module: Module, slot: int, sounded_note: Note, row: int) -> None:
    PostgresNoteEventRepository(connection).insert_many(
        [
            NoteEvent(
                module_id=module.id,
                pattern_index=0,
                row_index=row,
                channel_index=0,
                note=REFERENCE_KEY,
                sounded_note=sounded_note,
                instrument_index=0,
                sample_slot=slot,
            )
        ]
    )


def test_list_samples_returns_a_page(client: TestClient, connection: Connection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)

    response = client.get("/samples")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["hash"] for item in body["items"]} == {first.hash, second.hash}


def test_list_samples_ranks_by_occurrence_count(client: TestClient, connection: Connection) -> None:
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
    assert body["items"][0]["category"] == "kick"


def test_list_samples_falls_back_to_the_dominant_occurrence_rate(client: TestClient, connection: Connection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="kick", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="kick", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=2, name="kick", rate=22050)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["playback_rate_hz"] == 8363


def test_list_samples_leaves_the_playback_rate_null_for_a_sample_with_no_occurrences(
    client: TestClient, connection: Connection
) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["playback_rate_hz"] is None


def test_list_samples_includes_a_cached_thumbnail(client: TestClient, connection: Connection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    PostgresSampleThumbnailRepository(connection).upsert(
        SampleThumbnail(sample_hash=sample.hash, bucket_count=2, minimums=(-1.0, -0.5), maximums=(0.5, 1.0))
    )

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["thumbnail"] == [
        {"minimum": -1.0, "maximum": 0.5},
        {"minimum": -0.5, "maximum": 1.0},
    ]


def test_list_samples_leaves_thumbnail_null_when_not_yet_cached(client: TestClient, connection: Connection) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["thumbnail"] is None


def test_list_samples_respects_limit_and_offset(client: TestClient, connection: Connection) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)
    _insert_sample(connection, SAMPLE_HASH_B)

    response = client.get("/samples", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_samples_leaves_equivalence_fields_at_their_standalone_default(
    client: TestClient, connection: Connection
) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get("/samples")

    body = response.json()
    assert body["items"][0]["equivalence_class_hash"] is None
    assert body["items"][0]["equivalence_member_count"] == 1


def test_list_samples_resolves_an_equivalence_class_from_a_relation(client: TestClient, connection: Connection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    relation_repository = PostgresSampleRelationRepository(connection)
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=first.hash,
            reference_hash=second.hash,
            relation_type=RelationType.BIT_DEPTH_VARIANT,
            method="bit_depth_variant/mse_v1",
            confidence=0.9,
            evidence={"max_abs_error": 0.001},
            detected_at=datetime.now(UTC),
        )
    )

    response = client.get("/samples")

    body = response.json()
    by_hash = {item["hash"]: item for item in body["items"]}
    assert by_hash[first.hash]["equivalence_class_hash"] == by_hash[second.hash]["equivalence_class_hash"]
    assert by_hash[first.hash]["equivalence_member_count"] == 2
    assert by_hash[second.hash]["equivalence_member_count"] == 2


def test_list_samples_group_by_equivalence_collapses_the_class_into_one_representative(
    client: TestClient, connection: Connection
) -> None:
    frequent = _insert_sample(connection, SAMPLE_HASH_A)
    rare = _insert_sample(connection, SAMPLE_HASH_B)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=frequent, module=module, slot=0, name="kick")
    relation_repository = PostgresSampleRelationRepository(connection)
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=frequent.hash,
            reference_hash=rare.hash,
            relation_type=RelationType.BIT_DEPTH_VARIANT,
            method="bit_depth_variant/mse_v1",
            confidence=0.9,
            evidence={"max_abs_error": 0.001},
            detected_at=datetime.now(UTC),
        )
    )

    response = client.get("/samples", params={"group_by_equivalence": True})

    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["hash"] == frequent.hash
    assert body["items"][0]["equivalence_member_count"] == 2


def test_list_samples_group_by_equivalence_defaults_to_ungrouped(client: TestClient, connection: Connection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    relation_repository = PostgresSampleRelationRepository(connection)
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=first.hash,
            reference_hash=second.hash,
            relation_type=RelationType.BIT_DEPTH_VARIANT,
            method="bit_depth_variant/mse_v1",
            confidence=0.9,
            evidence={"max_abs_error": 0.001},
            detected_at=datetime.now(UTC),
        )
    )

    response = client.get("/samples")

    assert len(response.json()["items"]) == 2


def test_get_sample_returns_detail_with_occurrences_and_module_context(
    client: TestClient, connection: Connection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection, filename="song.xm", title="a song")
    _add_occurrence(connection, sample=sample, module=module, name="lead")

    response = client.get(f"/samples/{sample.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["hash"] == sample.hash
    assert body["display_name"] == "lead"
    assert body["category"] == "lead"
    assert len(body["occurrences"]) == 1
    occurrence = body["occurrences"][0]
    assert occurrence["properties"]["name"] == "lead"
    assert occurrence["module"] == {
        "hash": module.hash,
        "filename": "song.xm",
        "title": "a song",
        "tracker": "xm",
    }


def test_get_sample_falls_back_to_the_dominant_occurrence_rate(client: TestClient, connection: Connection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="lead", rate=22050)
    _add_occurrence(connection, sample=sample, module=module, slot=2, name="lead", rate=22050)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["playback_rate_hz"] == 22050


def test_get_sample_gathers_the_rates_its_note_events_really_sound(client: TestClient, connection: Connection) -> None:
    """Two occurrences an octave apart, played an octave apart, sound one and the same speed.

    The rate an event sounds at follows from the occurrence it reaches and the key struck against
    it, so both events here read the waveform at 16726 Hz and belong to one rate between them.
    """
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead", rate=8363)
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="lead", rate=16726)
    _play_note(connection, module=module, slot=0, sounded_note=OCTAVE_ABOVE_REFERENCE_KEY, row=0)
    _play_note(connection, module=module, slot=1, sounded_note=REFERENCE_KEY, row=1)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["playback_rates"] == [{"rate_hz": 16726, "event_count": 2}]
    assert body["playback_rate_hz"] == 16726


def test_get_sample_lists_the_most_played_rate_first(client: TestClient, connection: Connection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead", rate=8363)
    _play_note(connection, module=module, slot=0, sounded_note=REFERENCE_KEY, row=0)
    _play_note(connection, module=module, slot=0, sounded_note=OCTAVE_ABOVE_REFERENCE_KEY, row=1)
    _play_note(connection, module=module, slot=0, sounded_note=OCTAVE_ABOVE_REFERENCE_KEY, row=2)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["playback_rates"] == [
        {"rate_hz": 16726, "event_count": 2},
        {"rate_hz": 8363, "event_count": 1},
    ]
    assert body["playback_rate_hz"] == 16726


def test_get_sample_resolves_a_shared_module_only_once_across_occurrences(
    client: TestClient, connection: Connection
) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    module = _insert_module(connection)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead")
    _add_occurrence(connection, sample=sample, module=module, slot=1, name="lead")

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert len(body["occurrences"]) == 2
    assert {occurrence["module"]["hash"] for occurrence in body["occurrences"]} == {module.hash}


def test_get_sample_reports_size_and_duration(client: TestClient, connection: Connection) -> None:
    sample = _insert_sample(connection, SAMPLE_HASH_A, frames=audio_store.NOMINAL_WAV_RATE)

    response = client.get(f"/samples/{sample.hash}")

    body = response.json()
    assert body["size_bytes"] == sample.stored_bytes
    assert body["duration_seconds"] == 1.0


def test_get_sample_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}")

    assert response.status_code == 404


def test_get_sample_audio_serves_the_stored_wav_file(
    client: TestClient, connection: Connection, tmp_path: Path
) -> None:
    sample = Sample(hash=SAMPLE_HASH_A, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
    PostgresSampleRepository(connection).upsert(sample)
    pcm = np.zeros((4, 1), dtype=np.float64)
    audio_store.write(tmp_path, SamplePCM(sample=sample, pcm=pcm))

    response = client.get(f"/samples/{sample.hash}/audio")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"


def test_get_sample_audio_404s_for_an_unknown_hash(client: TestClient) -> None:
    response = client.get(f"/samples/{'f' * 64}/audio")

    assert response.status_code == 404


def test_get_sample_waveform_returns_peaks(client: TestClient, connection: Connection, tmp_path: Path) -> None:
    sample = Sample(hash=SAMPLE_HASH_A, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
    PostgresSampleRepository(connection).upsert(sample)
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


def test_get_sample_relations_returns_the_equivalence_class(client: TestClient, connection: Connection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    relation_repository = PostgresSampleRelationRepository(connection)
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


def test_get_sample_distance_computes_the_euclidean_distance_between_two_vectors(
    client: TestClient, connection: Connection
) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    feature_repository = PostgresSampleSpectralFeatureRepository(connection)
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=first.hash, vector=(0.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=second.hash, vector=(3.0, 4.0), computed_at=datetime.now(UTC))
    )

    response = client.get(f"/samples/{first.hash}/distance/{second.hash}")

    assert response.status_code == 200
    body = response.json()
    assert body["sample_hash"] == first.hash
    assert body["other_hash"] == second.hash
    assert body["distance"] == 5.0


def test_get_sample_distance_404s_when_either_sample_has_no_vector(client: TestClient, connection: Connection) -> None:
    first = _insert_sample(connection, SAMPLE_HASH_A)
    second = _insert_sample(connection, SAMPLE_HASH_B)
    PostgresSampleSpectralFeatureRepository(connection).upsert(
        SampleSpectralFeature(sample_hash=first.hash, vector=(0.0, 0.0), computed_at=datetime.now(UTC))
    )

    response = client.get(f"/samples/{first.hash}/distance/{second.hash}")

    assert response.status_code == 404


def test_get_similar_samples_orders_neighbors_by_ascending_distance(client: TestClient, connection: Connection) -> None:
    target = _insert_sample(connection, SAMPLE_HASH_A)
    near = _insert_sample(connection, SAMPLE_HASH_B)
    far = _insert_sample(connection, "c" * 64)
    feature_repository = PostgresSampleSpectralFeatureRepository(connection)
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=target.hash, vector=(0.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=near.hash, vector=(1.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=far.hash, vector=(5.0, 0.0), computed_at=datetime.now(UTC))
    )

    response = client.get(f"/samples/{target.hash}/similar")

    assert response.status_code == 200
    body = response.json()
    assert [item["hash"] for item in body] == [near.hash, far.hash]


def test_get_similar_samples_carry_the_rate_to_hear_them_at(client: TestClient, connection: Connection) -> None:
    target = _insert_sample(connection, SAMPLE_HASH_A)
    neighbor = _insert_sample(connection, SAMPLE_HASH_B)
    feature_repository = PostgresSampleSpectralFeatureRepository(connection)
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=target.hash, vector=(0.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=neighbor.hash, vector=(1.0, 0.0), computed_at=datetime.now(UTC))
    )
    PostgresSamplePlaybackRateRepository(connection).replace_all({neighbor.hash: 22050})

    response = client.get(f"/samples/{target.hash}/similar")

    assert [item["playback_rate_hz"] for item in response.json()] == [22050]


def test_get_similar_samples_respects_the_limit(client: TestClient, connection: Connection) -> None:
    target = _insert_sample(connection, SAMPLE_HASH_A)
    near = _insert_sample(connection, SAMPLE_HASH_B)
    far = _insert_sample(connection, "c" * 64)
    feature_repository = PostgresSampleSpectralFeatureRepository(connection)
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=target.hash, vector=(0.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=near.hash, vector=(1.0, 0.0), computed_at=datetime.now(UTC))
    )
    feature_repository.upsert(
        SampleSpectralFeature(sample_hash=far.hash, vector=(5.0, 0.0), computed_at=datetime.now(UTC))
    )

    response = client.get(f"/samples/{target.hash}/similar", params={"limit": 1})

    body = response.json()
    assert [item["hash"] for item in body] == [near.hash]


def test_get_similar_samples_404s_when_the_target_has_no_vector(client: TestClient, connection: Connection) -> None:
    _insert_sample(connection, SAMPLE_HASH_A)

    response = client.get(f"/samples/{SAMPLE_HASH_A}/similar")

    assert response.status_code == 404
