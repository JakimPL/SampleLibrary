from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.suggestions.scoring import show_scoring
from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.experiment import VOCABULARY_PARAMETER, ZERO_SHOT_BACKEND_NAME
from samplecore.models.label_suggestion import SampleLabelSuggestion
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.playback_rate import (
    PostgresSamplePlaybackRateRepository,
)
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository

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
    assert "hand_label" not in body[0]
    assert "computed_at" not in body[0]


def test_get_cloud_rounds_each_coordinate_to_what_a_viewer_can_place(
    client: TestClient, connection: Connection
) -> None:
    PostgresSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.23456789, y=-2.98765432, computed_at=datetime.now(UTC))
    )

    body = client.get("/cloud").json()

    assert body[0]["x"] == 1.2346
    assert body[0]["y"] == -2.9877


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


def test_the_cloud_follows_a_fresh_embedding_and_a_replaced_rate(client: TestClient, connection: Connection) -> None:
    """The answer is served from memory until the rows behind it move, and every kind of move reaches the next answer."""
    _store_samples(connection, SAMPLE_HASH, "b" * 64)
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )
    assert len(client.get("/cloud").json()) == 1
    assert client.get("/cloud").json()[0]["playback_rate_hz"] is None

    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash="b" * 64, x=0.5, y=0.5, computed_at=datetime.now(UTC))
    )
    assert len(client.get("/cloud").json()) == 2

    PostgresSamplePlaybackRateRepository(connection).replace_all({SAMPLE_HASH: 8363})
    by_hash = {point["sample_hash"]: point for point in client.get("/cloud").json()}

    assert by_hash[SAMPLE_HASH]["playback_rate_hz"] == 8363

    PostgresSamplePlaybackRateRepository(connection).replace_all({SAMPLE_HASH: 16726})
    by_hash = {point["sample_hash"]: point for point in client.get("/cloud").json()}

    assert by_hash[SAMPLE_HASH]["playback_rate_hz"] == 16726


def test_the_cloud_follows_a_scanned_sample_file(client: TestClient, connection: Connection) -> None:
    _store_samples(connection, SAMPLE_HASH)
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )
    assert client.get("/cloud").json()[0]["playback_rate_hz"] is None

    PostgresSampleFileRepository(connection).upsert(
        SampleFile(
            sample_hash=SAMPLE_HASH,
            location=SampleFileLocation(directory=Path("/samples"), relative_path="Snares/001.wav"),
            rate=44100,
            fingerprint=FileFingerprint(size_bytes=64, modified_ns=0),
        )
    )
    point = client.get("/cloud").json()[0]

    assert point["playback_rate_hz"] == 44100


def test_the_cloud_goes_out_gzipped_only_when_the_caller_accepts_it(client: TestClient, connection: Connection) -> None:
    _store_samples(connection, SAMPLE_HASH)
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=SAMPLE_HASH, x=1.5, y=-2.5, computed_at=datetime.now(UTC))
    )

    compressed = client.get("/cloud", headers={"Accept-Encoding": "gzip"})
    plain = client.get("/cloud", headers={"Accept-Encoding": "identity"})

    assert compressed.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in plain.headers
    assert compressed.json() == plain.json()
    assert plain.headers["vary"] == "Accept-Encoding"


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
    assert "computed_at" not in body[0]


def test_get_module_cloud_on_an_empty_catalog_returns_nothing(client: TestClient) -> None:
    response = client.get("/cloud/modules")

    assert response.status_code == 200
    assert response.json() == []


def test_get_cloud_labels_carries_each_labeled_sample_s_tags_in_the_order_written(
    client: TestClient, connection: Connection
) -> None:
    """A rating alone names no tag, so only the labeled sample comes back."""
    for sample_hash in (SAMPLE_HASH, "b" * 64):
        PostgresSampleRepository(connection).upsert(
            Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
        )
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            _annotation(SAMPLE_HASH, label="SYNTH: PULSE, CHIPTUNE", rating=None),
            _annotation("b" * 64, label=None, rating=4),
        )
    )

    response = client.get("/cloud/labels")

    assert response.status_code == 200
    assert response.json() == [{"sample_hash": SAMPLE_HASH, "paths": [["SYNTH", "PULSE"], ["CHIPTUNE"]]}]


def test_get_cloud_labels_on_an_unlabeled_catalog_returns_nothing(client: TestClient) -> None:
    assert client.get("/cloud/labels").json() == []


VOCABULARY = ("SNARE", "BASS DRUM", "HI-HAT: CLOSED")


def seed_scoring(connection: Connection, picks: dict[str, tuple[tuple[str, float], ...]]) -> int:
    """A scoring over the catalog: each sample's suggested labels with scores, closest first, under one experiment."""
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name=ZERO_SHOT_BACKEND_NAME, label=None, params={VOCABULARY_PARAMETER: list(VOCABULARY)}, key=None
    )
    PostgresSampleLabelSuggestionRepository(connection).insert_many(
        [
            SampleLabelSuggestion(
                experiment_id=experiment_id,
                sample_hash=sample_hash,
                rank=rank,
                label=label,
                score=score,
                computed_at=datetime.now(UTC),
            )
            for sample_hash, suggestions in picks.items()
            for rank, (label, score) in enumerate(suggestions)
        ]
    )
    show_scoring(connection, experiment_id)
    return experiment_id


def _store_samples(connection: Connection, *hashes: str) -> None:
    for sample_hash in hashes:
        PostgresSampleRepository(connection).upsert(
            Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
        )


def test_get_cloud_suggestions_carries_each_sample_s_closest_pick(client: TestClient, connection: Connection) -> None:
    _store_samples(connection, SAMPLE_HASH)
    seed_scoring(connection, {SAMPLE_HASH: (("HI-HAT: CLOSED", 0.7), ("SNARE", 0.4))})

    response = client.get("/cloud/suggestions")

    assert response.status_code == 200
    assert response.json() == [{"sample_hash": SAMPLE_HASH, "path": ["HI-HAT", "CLOSED"], "score": 0.7}]


def test_get_cloud_suggestions_reads_the_scoring_on_show_alone(client: TestClient, connection: Connection) -> None:
    """Showing a scoring reaches the next answer, an earlier one shown again included: the shown scoring is the revision."""
    _store_samples(connection, SAMPLE_HASH)
    earlier = seed_scoring(connection, {SAMPLE_HASH: (("SNARE", 0.5),)})
    assert [entry["path"] for entry in client.get("/cloud/suggestions").json()] == [["SNARE"]]

    seed_scoring(connection, {SAMPLE_HASH: (("BASS DRUM", 0.6),)})
    assert [entry["path"] for entry in client.get("/cloud/suggestions").json()] == [["BASS DRUM"]]
    show_scoring(connection, earlier)
    body = client.get("/cloud/suggestions").json()

    assert [entry["path"] for entry in body] == [["SNARE"]]


def test_get_cloud_suggestion_tags_rank_by_the_scoring_s_vocabulary_and_count_first_picks(
    client: TestClient, connection: Connection
) -> None:
    """The closed hat is picked first twice, counting toward the hat category; a tag outside the vocabulary ranks last."""
    _store_samples(connection, SAMPLE_HASH, "b" * 64, "d" * 64, "e" * 64)
    seed_scoring(
        connection,
        {
            SAMPLE_HASH: (("HI-HAT: CLOSED", 0.7), ("SNARE", 0.4)),
            "b" * 64: (("HI-HAT: CLOSED", 0.6),),
            "d" * 64: (("SNARE", 0.9),),
            "e" * 64: (("PIANO", 0.9),),
        },
    )

    response = client.get("/cloud/suggestion-tags")

    assert response.status_code == 200
    assert response.json() == [
        {"path": ["SNARE"], "sample_count": 1, "rank": 0},
        {"path": ["HI-HAT"], "sample_count": 2, "rank": 2},
        {"path": ["HI-HAT", "CLOSED"], "sample_count": 2, "rank": 3},
        {"path": ["PIANO"], "sample_count": 1, "rank": 4},
    ]


def test_cloud_suggestions_on_a_catalog_without_a_scoring_return_nothing(client: TestClient) -> None:
    assert client.get("/cloud/suggestions").json() == []
    assert client.get("/cloud/suggestion-tags").json() == []


def _annotation(sample_hash: str, *, label: str | None, rating: int | None) -> SampleAnnotation:
    return SampleAnnotation(
        label=label,
        rating=rating,
        favorite=False,
        sample_hash=sample_hash,
        anchor=ModuleSlotAnchor(
            occurrence=SampleOccurrence(module_hash=MODULE_HASH, instrument_index=0, sample_slot=0),
            module_filename="song.xm",
            sample_name="a sample",
        ),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )
