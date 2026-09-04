from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from samplecore.models.relation import RelationType, SampleRelation


def _relation(subject_hash: str, reference_hash: str) -> SampleRelation:
    return SampleRelation(
        id=0,
        subject_hash=subject_hash,
        reference_hash=reference_hash,
        relation_type=RelationType.BIT_DEPTH_VARIANT,
        method="bit_depth_variant/mse_v1",
        confidence=0.95,
        evidence={"max_abs_error": 0.001},
        detected_at=datetime.now(UTC),
    )


def test_a_relation_between_two_distinct_ordered_hashes_is_accepted(sample_hash_a: str, sample_hash_b: str) -> None:
    relation = _relation(sample_hash_a, sample_hash_b)

    assert relation.review is None


def test_a_sample_cannot_be_related_to_itself(sample_hash_a: str) -> None:
    with pytest.raises(ValidationError, match="related to itself"):
        _relation(sample_hash_a, sample_hash_a)


def test_the_subject_hash_must_be_the_smaller_of_the_two(sample_hash_a: str, sample_hash_b: str) -> None:
    with pytest.raises(ValidationError, match="lexicographically smaller"):
        _relation(sample_hash_b, sample_hash_a)


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_outside_the_unit_interval_is_rejected(
    sample_hash_a: str, sample_hash_b: str, confidence: float
) -> None:
    with pytest.raises(ValidationError):
        SampleRelation(
            id=0,
            subject_hash=sample_hash_a,
            reference_hash=sample_hash_b,
            relation_type=RelationType.RESAMPLED_VARIANT,
            method="resampled_variant/xcorr_v1",
            confidence=confidence,
            evidence={},
            detected_at=datetime.now(UTC),
        )
