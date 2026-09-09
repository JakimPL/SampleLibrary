from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64
UNKNOWN_SAMPLE_HASH = "f" * 64

NOTHING: dict[str, Any] = {"label": None, "rating": None, "favorite": False}


def _state(**decisions: Any) -> dict[str, Any]:
    """A whole annotation state, since every write says what a sample carries from then on."""
    return NOTHING | decisions


def _insert_sample(connection: Connection, sample_hash: str) -> Sample:
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    PostgresSampleRepository(connection).upsert(sample)
    return sample


def _insert_module(connection: Connection) -> Module:
    repository = PostgresModuleRepository(connection)
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


def _add_occurrence(connection: Connection, *, sample: Sample, module: Module, slot: int, name: str) -> None:
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name=name,
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def _relate(connection: Connection) -> None:
    repository = PostgresSampleRelationRepository(connection)
    repository.upsert(
        SampleRelation(
            id=repository.next_id(),
            subject_hash=SAMPLE_HASH_A,
            reference_hash=SAMPLE_HASH_B,
            relation_type=RelationType.AMPLIFICATION_VARIANT,
            method="test",
            confidence=1.0,
            evidence={},
            detected_at=datetime.now(UTC),
        )
    )


def _seed_one_sample(connection: Connection) -> Sample:
    module = _insert_module(connection)
    sample = _insert_sample(connection, SAMPLE_HASH_A)
    _add_occurrence(connection, sample=sample, module=module, slot=0, name="lead")
    return sample


def _seed_a_pair_of_near_duplicates(connection: Connection) -> None:
    module = _insert_module(connection)
    for slot, (sample_hash, name) in enumerate([(SAMPLE_HASH_A, "lead"), (SAMPLE_HASH_B, "lead quiet")]):
        _add_occurrence(connection, sample=_insert_sample(connection, sample_hash), module=module, slot=slot, name=name)

    _relate(connection)


def test_annotating_a_sample_records_every_decision_that_was_made(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}",
        json=_state(label="warm pad", rating=4, favorite=True, scope="sample"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "annotation": {"label": "WARM PAD", "rating": 4, "favorite": True},
        "sample_hashes": [SAMPLE_HASH_A],
    }


def test_a_rating_may_be_recorded_without_any_wording(client: TestClient, connection: Connection) -> None:
    """Deciding a sample is good is a decision of its own, made long before deciding what it is."""
    _seed_one_sample(connection)

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(rating=5, scope="sample"))

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()
    assert (body["hand_label"], body["rating"], body["favorite"]) == (None, 5, False)


def test_an_annotation_is_anchored_to_the_module_slot_it_was_found_in(
    client: TestClient, connection: Connection
) -> None:
    """The anchor is what lets a decision be found again after the sample's hash changes."""
    _seed_one_sample(connection)

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="warm pad", scope="sample"))

    stored = PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH_A)
    assert stored is not None
    assert stored.occurrence == SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0)
    assert stored.module_filename == "song.xm"
    assert stored.sample_name == "lead"


def test_an_annotated_sample_reports_its_decisions_in_its_own_detail(
    client: TestClient, connection: Connection
) -> None:
    _seed_one_sample(connection)
    client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}",
        json=_state(label="warm pad", rating=3, favorite=True, scope="sample"),
    )

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()

    assert (body["hand_label"], body["rating"], body["favorite"]) == ("WARM PAD", 3, True)
    assert body["category"] == "lead"


def test_an_annotated_sample_reports_its_decisions_in_the_listing(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}",
        json=_state(label="warm pad", rating=2, favorite=True, scope="sample"),
    )

    items = client.get("/samples").json()["items"]

    assert [(item["hand_label"], item["rating"], item["favorite"]) for item in items] == [("WARM PAD", 2, True)]


def test_an_untouched_sample_carries_no_decisions(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()

    assert (body["hand_label"], body["rating"], body["favorite"]) == (None, None, False)


def test_annotating_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    response = client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}",
        json=_state(label="snare", rating=4, scope="equivalence_class"),
    )

    assert sorted(response.json()["sample_hashes"]) == sorted([SAMPLE_HASH_A, SAMPLE_HASH_B])
    stored = PostgresSampleAnnotationRepository(connection).annotations_by_hash([SAMPLE_HASH_A, SAMPLE_HASH_B])
    assert {hash_: (item.label, item.rating) for hash_, item in stored.items()} == {
        SAMPLE_HASH_A: ("SNARE", 4),
        SAMPLE_HASH_B: ("SNARE", 4),
    }


def test_annotating_a_sample_only_leaves_its_near_duplicates_alone(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="snare", scope="sample"))

    assert PostgresSampleAnnotationRepository(connection).annotations_by_hash([SAMPLE_HASH_B]) == {}


def test_a_group_gesture_records_that_the_decision_was_inherited(client: TestClient, connection: Connection) -> None:
    """A sample nobody listened to individually is weaker evidence, and stays marked as such."""
    _seed_a_pair_of_near_duplicates(connection)

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="snare", scope="equivalence_class"))

    stored = PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH_B)
    assert stored is not None
    assert stored.source.value == "equivalence_class"


def test_a_sample_with_no_near_duplicates_is_its_own_whole_group(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="kick", scope="equivalence_class")
    )

    assert response.json()["sample_hashes"] == [SAMPLE_HASH_A]


def test_a_detail_reports_how_many_samples_a_group_gesture_would_reach(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["equivalence_member_count"] == 2


def test_writing_again_replaces_every_decision_including_the_ones_left_empty(
    client: TestClient, connection: Connection
) -> None:
    _seed_one_sample(connection)
    client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}",
        json=_state(label="lead", rating=5, favorite=True, scope="sample"),
    )

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="pluck", scope="sample"))

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()
    assert (body["hand_label"], body["rating"], body["favorite"]) == ("PLUCK", None, False)


def test_a_state_recording_nothing_takes_the_annotation_back(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="lead", scope="sample"))

    response = client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(scope="sample"))

    assert response.status_code == 200
    assert response.json()["annotation"] is None
    assert PostgresSampleAnnotationRepository(connection).count() == 0


def test_taking_back_over_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="snare", scope="equivalence_class"))

    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(scope="equivalence_class"))

    assert PostgresSampleAnnotationRepository(connection).count() == 0


def test_a_group_member_the_catalog_holds_no_occurrence_for_is_left_saying_nothing(
    client: TestClient, connection: Connection
) -> None:
    """A member with nowhere to anchor cannot carry the group's decision, so it carries none."""
    module = _insert_module(connection)
    _add_occurrence(connection, sample=_insert_sample(connection, SAMPLE_HASH_A), module=module, slot=0, name="lead")
    _insert_sample(connection, SAMPLE_HASH_B)
    _relate(connection)
    repository = PostgresSampleAnnotationRepository(connection)
    repository.replace_many(
        (
            SampleAnnotation(
                sample_hash=SAMPLE_HASH_B,
                label="stale",
                rating=None,
                favorite=False,
                occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=9),
                module_filename="song.xm",
                sample_name="gone",
                source=AnnotationSource.EQUIVALENCE_CLASS,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    connection.commit()

    response = client.put(
        f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="clap", scope="equivalence_class")
    )

    assert sorted(response.json()["sample_hashes"]) == sorted([SAMPLE_HASH_A, SAMPLE_HASH_B])
    assert repository.get(SAMPLE_HASH_B) is None
    assert repository.count() == 1


def test_annotating_a_sample_the_catalog_lacks_is_refused(client: TestClient) -> None:
    response = client.put(f"/curation/annotations/{UNKNOWN_SAMPLE_HASH}", json=_state(label="kick", scope="sample"))

    assert response.status_code == 404


def test_a_label_saying_nothing_is_refused(client: TestClient, connection: Connection) -> None:
    """Blank text is malformed rather than a way to clear a label, which arrives as null instead."""
    _seed_one_sample(connection)

    response = client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="   ", scope="sample"))

    assert response.status_code == 422


def test_a_rating_outside_the_scale_is_refused(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(rating=6, scope="sample"))

    assert response.status_code == 422


def test_the_vocabulary_offers_back_what_has_already_been_chosen(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="snare", scope="sample"))
    client.put(f"/curation/annotations/{SAMPLE_HASH_B}", json=_state(label="clap", scope="sample"))

    assert sorted(client.get("/curation/annotations/vocabulary").json()) == ["CLAP", "SNARE"]


def test_the_vocabulary_gathers_one_entry_however_a_wording_was_typed(
    client: TestClient, connection: Connection
) -> None:
    """A label is stored in one case, so two typings of one wording offer back one entry."""
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(label="Warm Pad", scope="sample"))
    client.put(f"/curation/annotations/{SAMPLE_HASH_B}", json=_state(label="warm pad", scope="sample"))

    assert client.get("/curation/annotations/vocabulary").json() == ["WARM PAD"]


def test_the_vocabulary_of_an_unlabeled_library_is_empty(client: TestClient) -> None:
    assert client.get("/curation/annotations/vocabulary").json() == []


def test_a_listing_narrowed_to_favorites_reaches_only_what_was_marked(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(favorite=True, scope="sample"))

    body = client.get("/samples", params={"favorites_only": True}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_A]
    assert body["total"] == 1


def test_a_listing_narrowed_by_rating_keeps_only_what_reaches_the_floor(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(rating=5, scope="sample"))
    client.put(f"/curation/annotations/{SAMPLE_HASH_B}", json=_state(rating=1, scope="sample"))

    body = client.get("/samples", params={"minimum_rating": 3}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_A]
    assert body["total"] == 1


def test_a_listing_sorted_by_rating_puts_the_best_first(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json=_state(rating=2, scope="sample"))
    client.put(f"/curation/annotations/{SAMPLE_HASH_B}", json=_state(rating=5, scope="sample"))

    body = client.get("/samples", params={"sort": "rating"}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_B, SAMPLE_HASH_A]


def test_a_rating_floor_outside_the_scale_is_refused(client: TestClient) -> None:
    assert client.get("/samples", params={"minimum_rating": 9}).status_code == 422
