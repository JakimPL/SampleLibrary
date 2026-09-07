from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

SAMPLE_HASH_A = "a" * 64
SAMPLE_HASH_B = "b" * 64
UNKNOWN_SAMPLE_HASH = "f" * 64


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


def test_labelling_a_sample_records_the_wording_that_was_chosen(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "warm pad", "scope": "sample"})

    assert response.status_code == 200
    assert response.json() == {"label": "warm pad", "sample_hashes": [SAMPLE_HASH_A]}


def test_a_label_is_anchored_to_the_module_slot_it_was_found_in(client: TestClient, connection: Connection) -> None:
    """The anchor is what lets the label be found again after the sample's hash changes."""
    _seed_one_sample(connection)

    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "warm pad", "scope": "sample"})

    stored = PostgresSampleLabelRepository(connection).get(SAMPLE_HASH_A)
    assert stored is not None
    assert stored.occurrence == SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0)
    assert stored.module_filename == "song.xm"
    assert stored.sample_name == "lead"


def test_a_labelled_sample_reports_its_label_in_its_own_detail(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "warm pad", "scope": "sample"})

    body = client.get(f"/samples/{SAMPLE_HASH_A}").json()

    assert body["hand_label"] == "warm pad"
    assert body["category"] == "lead"


def test_a_labelled_sample_reports_its_label_in_the_listing(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "warm pad", "scope": "sample"})

    items = client.get("/samples").json()["items"]

    assert [item["hand_label"] for item in items] == ["warm pad"]


def test_an_unlabelled_sample_carries_no_label(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["hand_label"] is None


def test_labelling_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    response = client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "snare", "scope": "equivalence_class"})

    assert sorted(response.json()["sample_hashes"]) == sorted([SAMPLE_HASH_A, SAMPLE_HASH_B])
    assert PostgresSampleLabelRepository(connection).labels_by_hash([SAMPLE_HASH_A, SAMPLE_HASH_B]) == {
        SAMPLE_HASH_A: "snare",
        SAMPLE_HASH_B: "snare",
    }


def test_labelling_a_sample_only_leaves_its_near_duplicates_alone(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "snare", "scope": "sample"})

    assert PostgresSampleLabelRepository(connection).labels_by_hash([SAMPLE_HASH_B]) == {}


def test_a_sample_with_no_near_duplicates_is_its_own_whole_group(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "kick", "scope": "equivalence_class"})

    assert response.json()["sample_hashes"] == [SAMPLE_HASH_A]


def test_a_detail_reports_how_many_samples_a_group_label_would_reach(
    client: TestClient, connection: Connection
) -> None:
    _seed_a_pair_of_near_duplicates(connection)

    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["equivalence_member_count"] == 2


def test_relabelling_replaces_the_previous_choice(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "lead", "scope": "sample"})

    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "pluck", "scope": "sample"})

    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["hand_label"] == "pluck"


def test_clearing_a_label_takes_the_decision_back(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "lead", "scope": "sample"})

    response = client.delete(f"/curation/labels/{SAMPLE_HASH_A}")

    assert response.status_code == 200
    assert client.get(f"/samples/{SAMPLE_HASH_A}").json()["hand_label"] is None


def test_clearing_over_a_group_reaches_every_near_duplicate(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "snare", "scope": "equivalence_class"})

    client.delete(f"/curation/labels/{SAMPLE_HASH_A}?scope=equivalence_class")

    assert PostgresSampleLabelRepository(connection).count() == 0


def test_labelling_a_sample_the_catalog_lacks_is_refused(client: TestClient) -> None:
    response = client.put(f"/curation/labels/{UNKNOWN_SAMPLE_HASH}", json={"label": "kick", "scope": "sample"})

    assert response.status_code == 404


def test_a_label_saying_nothing_is_refused(client: TestClient, connection: Connection) -> None:
    _seed_one_sample(connection)

    response = client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "   ", "scope": "sample"})

    assert response.status_code == 422


def test_the_vocabulary_offers_back_what_has_already_been_chosen(client: TestClient, connection: Connection) -> None:
    _seed_a_pair_of_near_duplicates(connection)
    client.put(f"/curation/labels/{SAMPLE_HASH_A}", json={"label": "snare", "scope": "sample"})
    client.put(f"/curation/labels/{SAMPLE_HASH_B}", json={"label": "clap", "scope": "sample"})

    assert sorted(client.get("/curation/labels/vocabulary").json()) == ["clap", "snare"]


def test_the_vocabulary_of_an_unlabelled_library_is_empty(client: TestClient) -> None:
    assert client.get("/curation/labels/vocabulary").json() == []
