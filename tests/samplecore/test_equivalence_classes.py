from __future__ import annotations

from datetime import UTC, datetime

from samplecore.equivalence_classes import classes_by_member_hash, compute_equivalence_classes
from samplecore.hashing import compute_equivalence_class_hash
from samplecore.models.relation import RelationType, SampleRelation

HASH_NINE = "9" * 64
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


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


def test_no_relations_produce_no_classes() -> None:
    assert compute_equivalence_classes(()) == ()


def test_a_single_relation_forms_one_class_with_both_members() -> None:
    classes = compute_equivalence_classes((_relation(HASH_A, HASH_B),))

    assert len(classes) == 1
    assert set(classes[0].member_hashes) == {HASH_A, HASH_B}


def test_a_chain_of_relations_collapses_transitively_into_one_class() -> None:
    classes = compute_equivalence_classes((_relation(HASH_NINE, HASH_A), _relation(HASH_A, HASH_B)))

    assert len(classes) == 1
    assert set(classes[0].member_hashes) == {HASH_NINE, HASH_A, HASH_B}


def test_two_disjoint_relations_form_two_separate_classes() -> None:
    classes = compute_equivalence_classes((_relation(HASH_A, HASH_B), _relation(HASH_E, HASH_F)))

    member_sets = {classes[0].member_hashes, classes[1].member_hashes}
    assert len(classes) == 2
    assert member_sets == {(HASH_A, HASH_B), (HASH_E, HASH_F)}


def test_a_class_hash_matches_the_domain_hash_of_its_sorted_members() -> None:
    classes = compute_equivalence_classes((_relation(HASH_A, HASH_B),))

    assert classes[0].class_hash == compute_equivalence_class_hash((HASH_A, HASH_B))


def test_relation_order_does_not_change_the_resulting_classes() -> None:
    forward = compute_equivalence_classes((_relation(HASH_NINE, HASH_A), _relation(HASH_A, HASH_B)))
    reversed_ = compute_equivalence_classes((_relation(HASH_A, HASH_B), _relation(HASH_NINE, HASH_A)))

    assert forward == reversed_


def test_classes_by_member_hash_indexes_every_member() -> None:
    classes = compute_equivalence_classes((_relation(HASH_A, HASH_B), _relation(HASH_E, HASH_F)))

    index = classes_by_member_hash(classes)

    assert index[HASH_A] == index[HASH_B]
    assert index[HASH_E] == index[HASH_F]
    assert index[HASH_A] != index[HASH_E]


def test_classes_by_member_hash_omits_hashes_with_no_relation() -> None:
    classes = compute_equivalence_classes((_relation(HASH_A, HASH_B),))

    assert HASH_E not in classes_by_member_hash(classes)
