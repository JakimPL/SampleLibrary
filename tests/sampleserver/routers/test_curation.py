from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
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
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from samplecore.storage.repositories.sample_properties import (
    PostgresSamplePropertiesRepository,
)

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64
UNKNOWN_SAMPLE_HASH = "f" * 64


def _change(client: TestClient, sample_hash: str, *, scope: str = "sample", **decisions: Any) -> Response:
    """Send one gesture's change, naming only the decisions it changes."""
    return client.patch(f"/curation/annotations/{sample_hash}", json={"scope": scope} | decisions)


def _decisions(client: TestClient, sample_hash: str) -> tuple[Any, Any, Any]:
    body = client.get(f"/samples/{sample_hash}").json()
    return body["hand_label"], body["rating"], body["favorite"]


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

    response = _change(client, SAMPLE_HASH_A, label="warm pad", rating=4, favorite=True)

    assert response.status_code == 200
    assert response.json() == {
        "samples": [{"sample_hash": SAMPLE_HASH_A, "annotation": {"label": "WARM PAD", "rating": 4, "favorite": True}}],
        "skipped": [],
    }


def test_a_rating_may_be_recorded_without_any_wording(client: TestClient, connection: Connection) -> None:
    """Deciding a sample is good is a decision of its own, made long before deciding what it is."""
    _seed_one_sample(connection)

    _change(client, SAMPLE_HASH_A, rating=5)

    assert _decisions(client, SAMPLE_HASH_A) == (None, 5, False)


def test_an_annotation_is_anchored_to_the_module_slot_it_was_found_in(
    client: TestClient, connection: Connection
) -> None:
    """The anchor is what lets a decision be found again after the sample's hash changes."""
    _seed_one_sample(connection)

    _change(client, SAMPLE_HASH_A, label="warm pad")

    stored = PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH_A)
    assert stored is not None
    assert stored.occurrence == SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0)
    assert stored.module_filename == "song.xm"
    assert stored.sample_name == "lead"


def test_an_annotated_sample_reports_its_decisions_in_its_own_detail(
    client: TestClient, connection: Connection
) -> None:
    _seed_one_sample(connection)
    _change(client, SAMPLE_HASH_A, label="warm pad", rating=3, favorite=True)

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()

    assert (body["hand_label"], body["rating"], body["favorite"]) == ("WARM PAD", 3, True)
    assert body["category"] == "lead"


def test_an_annotated_sample_reports_its_decisions_in_the_listing(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    _change(client, SAMPLE_HASH_A, label="warm pad", rating=2, favorite=True)

    items = client.get("/samples").json()["items"]

    assert [(item["hand_label"], item["rating"], item["favorite"]) for item in items] == [("WARM PAD", 2, True)]


def test_an_untouched_sample_carries_no_decisions(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    assert _decisions(client, SAMPLE_HASH_A) == (None, None, False)


def test_annotating_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    response = _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="snare", rating=4)

    assert sorted(item["sample_hash"] for item in response.json()["samples"]) == sorted([SAMPLE_HASH_A, SAMPLE_HASH_B])
    stored = PostgresSampleAnnotationRepository(connection).annotations_by_hash([SAMPLE_HASH_A, SAMPLE_HASH_B])
    assert {hash_: (item.label, item.rating) for hash_, item in stored.items()} == {
        SAMPLE_HASH_A: ("SNARE", 4),
        SAMPLE_HASH_B: ("SNARE", 4),
    }


def test_annotating_a_sample_only_leaves_its_near_duplicates_alone(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    _change(client, SAMPLE_HASH_A, label="snare")

    assert PostgresSampleAnnotationRepository(connection).annotations_by_hash([SAMPLE_HASH_B]) == {}


def test_a_group_gesture_keeps_every_members_own_say_on_what_it_leaves_alone(
    client: TestClient, connection: Connection
) -> None:
    """Labeling a group reaches every member's label, and each member keeps its own stars and heart."""
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, rating=5, favorite=True)
    _change(client, SAMPLE_HASH_B, rating=2)

    _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="snare")

    assert _decisions(client, SAMPLE_HASH_A) == ("SNARE", 5, True)
    assert _decisions(client, SAMPLE_HASH_B) == ("SNARE", 2, False)


def test_a_group_gesture_records_that_the_decision_was_inherited(client: TestClient, connection: Connection) -> None:
    """A sample nobody listened to individually is weaker evidence, and stays marked as such."""
    _seed_a_pair_of_near_duplicates(connection)

    _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="snare")

    stored = PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH_B)
    assert stored is not None
    assert stored.source.value == "equivalence_class"


def test_a_sample_with_no_near_duplicates_is_its_own_whole_group(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="kick")

    assert [item["sample_hash"] for item in response.json()["samples"]] == [SAMPLE_HASH_A]


def test_a_detail_reports_how_many_samples_a_group_gesture_would_reach(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["equivalence_member_count"] == 2


def test_a_change_keeps_the_decisions_it_leaves_out(client: TestClient, connection: Connection) -> None:
    """A star click right after typing a label keeps the label, whichever request lands first."""
    _seed_one_sample(connection)
    _change(client, SAMPLE_HASH_A, label="lead", rating=5, favorite=True)

    _change(client, SAMPLE_HASH_A, label="pluck")

    assert _decisions(client, SAMPLE_HASH_A) == ("PLUCK", 5, True)


def test_a_decision_sent_empty_is_cleared(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    _change(client, SAMPLE_HASH_A, label="lead", rating=5, favorite=True)

    _change(client, SAMPLE_HASH_A, rating=None, favorite=False)

    assert _decisions(client, SAMPLE_HASH_A) == ("LEAD", None, False)


def test_clearing_the_last_decision_takes_the_annotation_back(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    _change(client, SAMPLE_HASH_A, label="lead")

    response = _change(client, SAMPLE_HASH_A, label=None)

    assert response.status_code == 200
    assert response.json()["samples"] == [{"sample_hash": SAMPLE_HASH_A, "annotation": None}]
    assert PostgresSampleAnnotationRepository(connection).count() == 0


def test_taking_back_over_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="snare")

    _change(client, SAMPLE_HASH_A, scope="equivalence_class", label=None)

    assert PostgresSampleAnnotationRepository(connection).count() == 0


def _seed_a_pair_with_an_unplaced_member(connection: Connection) -> Module:
    module = _insert_module(connection)
    _add_occurrence(connection, sample=_insert_sample(connection, SAMPLE_HASH_A), module=module, slot=0, name="lead")
    _insert_sample(connection, SAMPLE_HASH_B)
    _relate(connection)
    return module


def test_a_group_member_with_nothing_to_anchor_it_is_left_saying_nothing(
    client: TestClient, connection: Connection
) -> None:
    """A member with nowhere to anchor cannot carry the group's decision, so it carries none."""
    _seed_a_pair_with_an_unplaced_member(connection)

    response = _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="clap")

    assert response.json()["skipped"] == [SAMPLE_HASH_B]
    assert PostgresSampleAnnotationRepository(connection).get(SAMPLE_HASH_B) is None


def test_a_group_member_keeps_the_anchor_its_own_annotation_carries(client: TestClient, connection: Connection) -> None:
    module = _seed_a_pair_with_an_unplaced_member(connection)
    stored_anchor = SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=9)
    repository = PostgresSampleAnnotationRepository(connection)
    repository.upsert_many(
        (
            SampleAnnotation(
                sample_hash=SAMPLE_HASH_B,
                label="stale",
                rating=3,
                favorite=False,
                occurrence=stored_anchor,
                module_filename="song.xm",
                sample_name="gone",
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    connection.commit()

    _change(client, SAMPLE_HASH_A, scope="equivalence_class", label="clap")

    stored = repository.get(SAMPLE_HASH_B)
    assert stored is not None
    assert (stored.label, stored.rating, stored.occurrence) == ("CLAP", 3, stored_anchor)


def test_annotating_a_sample_neither_cataloged_nor_annotated_is_refused(client: TestClient) -> None:
    assert _change(client, UNKNOWN_SAMPLE_HASH, label="kick").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "sample", "label": "   "},
        {"scope": "sample", "label": ",,,"},
        {"scope": "sample", "rating": 6},
        {"scope": "sample", "rating": "3"},
        {"scope": "sample", "favorite": "yes"},
        {"scope": "sample", "favorite": None},
        {"scope": "sample"},
        {"scope": "sample", "label": "kick", "mood": "happy"},
    ],
    ids=(
        "blank label",
        "label naming no tag",
        "rating off the scale",
        "rating as text",
        "favorite as text",
        "favorite as null",
        "no decision",
        "an unknown field",
    ),
)
def test_a_malformed_change_is_refused(client: TestClient, connection: Connection, body: dict[str, Any]) -> None:
    """Blank text is malformed rather than a way to clear a label, which arrives as null instead."""
    _seed_one_sample(connection)

    assert client.patch(f"/curation/annotations/{SAMPLE_HASH_A}", json=body).status_code == 422


def test_a_malformed_hash_is_refused(client: TestClient) -> None:
    assert client.patch("/curation/annotations/NOT-A-HASH", json={"scope": "sample", "rating": 3}).status_code == 422


def test_an_annotation_whose_sample_left_the_catalog_can_be_changed_and_removed(
    client: TestClient, connection: Connection
) -> None:
    module = _insert_module(connection)
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            SampleAnnotation(
                sample_hash=UNKNOWN_SAMPLE_HASH,
                label="orphaned",
                rating=None,
                favorite=True,
                occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=3),
                module_filename="song.xm",
                sample_name="gone",
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    connection.commit()

    assert _change(client, UNKNOWN_SAMPLE_HASH, rating=2).status_code == 200
    assert client.delete(f"/curation/annotations/{UNKNOWN_SAMPLE_HASH}").status_code == 204
    assert PostgresSampleAnnotationRepository(connection).count() == 0


def test_removing_an_annotation_nobody_made_is_not_found(client: TestClient) -> None:
    assert client.delete(f"/curation/annotations/{UNKNOWN_SAMPLE_HASH}").status_code == 404


def test_the_vocabulary_offers_back_what_has_already_been_chosen(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, label="snare")
    _change(client, SAMPLE_HASH_B, label="clap")

    assert sorted(client.get("/curation/annotations/vocabulary").json()) == ["CLAP", "SNARE"]


def test_the_vocabulary_gathers_one_entry_however_a_wording_was_typed(
    client: TestClient, connection: Connection
) -> None:
    """A label is stored in one spelling, so two typings of one wording offer back one entry."""
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, label="Hi-Hat:closed")
    _change(client, SAMPLE_HASH_B, label="hi-hat :  CLOSED")

    assert client.get("/curation/annotations/vocabulary").json() == ["HI-HAT: CLOSED"]


def test_the_vocabulary_of_an_unlabeled_library_is_empty(client: TestClient) -> None:
    assert client.get("/curation/annotations/vocabulary").json() == []


def test_a_listing_narrowed_to_favorites_reaches_only_what_was_marked(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, favorite=True)

    body = client.get("/samples", params={"favorites_only": True}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_A]
    assert body["total"] == 1


def test_a_listing_narrowed_by_rating_keeps_only_what_reaches_the_floor(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, rating=5)
    _change(client, SAMPLE_HASH_B, rating=1)

    body = client.get("/samples", params={"minimum_rating": 3}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_A]
    assert body["total"] == 1


def test_a_listing_sorted_by_rating_puts_the_best_first(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, rating=2)
    _change(client, SAMPLE_HASH_B, rating=5)

    body = client.get("/samples", params={"sort": "rating"}).json()

    assert [item["hash"] for item in body["items"]] == [SAMPLE_HASH_B, SAMPLE_HASH_A]


def test_a_rating_floor_outside_the_scale_is_refused(client: TestClient) -> None:
    assert client.get("/samples", params={"minimum_rating": 9}).status_code == 422


def test_the_tags_read_the_paths_inside_the_labels_and_rank_them_by_first_use(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, label="hi-hat: closed, lo-fi")
    _change(client, SAMPLE_HASH_B, label="lo-fi, snare")

    tags = client.get("/curation/annotations/tags").json()

    assert [tag["path"] for tag in tags] == [["LO-FI"], ["HI-HAT"], ["HI-HAT", "CLOSED"], ["SNARE"]]
    assert {tuple(tag["path"]): tag["sample_count"] for tag in tags} == {
        ("LO-FI",): 2,
        ("HI-HAT",): 1,
        ("HI-HAT", "CLOSED"): 1,
        ("SNARE",): 1,
    }
    assert {tuple(tag["path"]): tag["rank"] for tag in tags} == {
        ("HI-HAT",): 0,
        ("HI-HAT", "CLOSED"): 1,
        ("LO-FI",): 2,
        ("SNARE",): 3,
    }


def test_a_tags_rank_stays_when_an_older_annotation_changes(client: TestClient, connection: Connection) -> None:
    """A viewer keeps one color per tag, however recently a sample carrying it was touched."""
    _seed_a_pair_of_near_duplicates(connection)
    _change(client, SAMPLE_HASH_A, label="kick")
    _change(client, SAMPLE_HASH_B, label="snare")

    _change(client, SAMPLE_HASH_A, rating=4)

    ranks = {tuple(tag["path"]): tag["rank"] for tag in client.get("/curation/annotations/tags").json()}
    assert ranks == {("KICK",): 0, ("SNARE",): 1}


def test_the_tags_of_an_unlabeled_library_are_none(client: TestClient) -> None:
    assert client.get("/curation/annotations/tags").json() == []


def test_a_whole_state_sent_by_put_is_no_longer_accepted(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(f"/curation/annotations/{SAMPLE_HASH_A}", json={"scope": "sample", "rating": 3})

    assert response.status_code == 405
