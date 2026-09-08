from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection

from samplecore.models.relation import RelationReview, RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository, _review_from_row


def _relation(relation_id: int, subject_hash: str, reference_hash: str, *, confidence: float = 0.9) -> SampleRelation:
    return SampleRelation(
        id=relation_id,
        subject_hash=subject_hash,
        reference_hash=reference_hash,
        relation_type=RelationType.BIT_DEPTH_VARIANT,
        method="bit_depth_variant/mse_v1",
        confidence=confidence,
        evidence={"max_abs_error": 0.001, "rms_error": 0.0002},
        detected_at=datetime.now(UTC),
    )


def test_an_unreviewed_relation_round_trips_through_get(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    relation = _relation(repository.next_id(), stored_sample.hash, stored_sample_b.hash)

    repository.upsert(relation)

    assert repository.get(relation.id) == relation


def test_reviewing_a_relation_populates_the_review_fields(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    relation = _relation(repository.next_id(), stored_sample.hash, stored_sample_b.hash)
    repository.upsert(relation)
    review = RelationReview(confirmed=True, reviewed_at=datetime.now(UTC), reviewed_by="jakim")

    repository.review(relation.id, review)

    round_tripped = repository.get(relation.id)
    assert round_tripped is not None
    assert round_tripped.review == review


def test_upserting_the_same_pair_and_method_again_updates_confidence(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    original = _relation(repository.next_id(), stored_sample.hash, stored_sample_b.hash, confidence=0.6)
    repository.upsert(original)
    refined = _relation(original.id, stored_sample.hash, stored_sample_b.hash, confidence=0.97)

    repository.upsert(refined)

    round_tripped = repository.get(original.id)
    assert round_tripped is not None
    assert round_tripped.confidence == 0.97


def test_get_on_an_unknown_id_returns_none(connection: Connection) -> None:
    repository = PostgresSampleRelationRepository(connection)

    assert repository.get(999) is None


def test_a_partially_populated_review_is_rejected_as_inconsistent() -> None:
    with pytest.raises(ValueError, match="set together"):
        _review_from_row(True, None, "jakim")


def test_list_all_on_an_empty_table_returns_nothing(connection: Connection) -> None:
    assert PostgresSampleRelationRepository(connection).list_all() == ()


def test_list_all_returns_every_stored_relation(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    relation = _relation(repository.next_id(), stored_sample.hash, stored_sample_b.hash)

    repository.upsert(relation)

    assert repository.list_all() == (relation,)


def test_list_for_sample_finds_a_relation_by_either_subject_or_reference_hash(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    relation = _relation(repository.next_id(), stored_sample.hash, stored_sample_b.hash)

    repository.upsert(relation)

    assert repository.list_for_sample(stored_sample.hash) == (relation,)
    assert repository.list_for_sample(stored_sample_b.hash) == (relation,)


def test_list_for_sample_finds_nothing_for_an_unrelated_sample(connection: Connection, sample_hash_a: str) -> None:
    assert PostgresSampleRelationRepository(connection).list_for_sample(sample_hash_a) == ()
