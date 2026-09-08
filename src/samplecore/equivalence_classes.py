from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from samplecore.hashing import compute_equivalence_class_hash
from samplecore.models.base import FROZEN
from samplecore.models.relation import SampleRelation
from samplecore.models.scalars import SampleHash


class EquivalenceClass(BaseModel):
    """A group of Samples the automatic detector considers near-duplicate variants of each other.

    ``class_hash`` is derived purely from the sorted set of member hashes, so the same group of
    samples always resolves to the same identity regardless of which relations were used to
    discover it or in what order they were traversed.
    """

    model_config = FROZEN

    class_hash: str
    member_hashes: tuple[SampleHash, ...]


def compute_equivalence_classes(relations: tuple[SampleRelation, ...]) -> tuple[EquivalenceClass, ...]:
    """Group Samples into equivalence classes via the connected components of their relations.

    Each SampleRelation -- already confidence-gated before being persisted -- is treated as an
    edge between its two sample hashes; every connected component of two or more samples becomes
    one class. A sample with no relation at all joins no class: membership means "known to be
    related to at least one other sample," not "every cataloged sample." Classes are returned
    ordered by ascending class hash, so the same relation set always yields the same sequence.
    """
    parents: dict[str, str] = {}

    def find(hash_: str) -> str:
        root = hash_
        while parents[root] != root:
            root = parents[root]
        while parents[hash_] != root:
            parents[hash_], hash_ = root, parents[hash_]
        return root

    def union(first: str, second: str) -> None:
        parents.setdefault(first, first)
        parents.setdefault(second, second)
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[first_root] = second_root

    for relation in relations:
        union(relation.subject_hash, relation.reference_hash)

    members_by_root: dict[str, set[str]] = defaultdict(set)
    for hash_ in parents:
        members_by_root[find(hash_)].add(hash_)

    classes = [
        EquivalenceClass(
            class_hash=compute_equivalence_class_hash(tuple(members)), member_hashes=tuple(sorted(members))
        )
        for members in members_by_root.values()
    ]
    return tuple(sorted(classes, key=lambda equivalence_class: equivalence_class.class_hash))


def classes_by_member_hash(classes: tuple[EquivalenceClass, ...]) -> dict[str, EquivalenceClass]:
    """Index a set of equivalence classes by every member hash they contain, for O(1) lookup."""
    return {
        member_hash: equivalence_class
        for equivalence_class in classes
        for member_hash in equivalence_class.member_hashes
    }
