from __future__ import annotations

from sqlalchemy import Connection

from samplecore.equivalence_classes import classes_by_member_hash, compute_equivalence_classes
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository


def equivalence_class_members(connection: Connection, sample_hash: str) -> tuple[str, ...]:
    """Every sample the detector treats as a near-duplicate of this one, the sample itself included.

    A sample with no detected relation forms a group of one, so this always names at least the hash
    it was asked about. That is what lets a single code path serve both a lone sample and a whole
    class: the group is simply smaller in the first case.
    """
    relations = PostgresSampleRelationRepository(connection).list_all()
    equivalence_class = classes_by_member_hash(compute_equivalence_classes(relations)).get(sample_hash)
    return equivalence_class.member_hashes if equivalence_class is not None else (sample_hash,)
