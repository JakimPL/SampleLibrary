from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import Connection

from samplecloud.evaluation.corpus import EvaluationCorpus, equivalence_groups, load_corpus
from samplecloud.standardization import Standardization
from samplecore.models.category import SampleCategory
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from tests.samplecloud.evaluation.conftest import SEEDED_CATEGORIES, SeededCatalog, seed_catalog


def test_a_corpus_carries_one_row_per_feature_vector(connection: Connection, separable_catalog: SeededCatalog) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    assert corpus.sample_count == len(separable_catalog.sample_hashes)
    assert corpus.vectors.shape[0] == corpus.sample_count
    assert len(corpus.categories) == corpus.sample_count


def test_a_corpus_classifies_each_sample_from_the_names_its_occurrences_carry(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    found = {str(category) for category in corpus.categories}
    assert found == set(SEEDED_CATEGORIES)
    assert corpus.categorized.all()


def test_a_corpus_reads_how_often_and_how_widely_each_sample_is_played(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    statistics = {
        str(category): entry
        for category, entry in zip(corpus.categories, corpus.note_statistics, strict=True)
        if entry is not None
    }
    assert corpus.note_reached.all()
    assert statistics["kick"].distinct_pitch_count == 1
    assert statistics["lead"].distinct_pitch_count == len(SEEDED_CATEGORIES)
    assert statistics["kick"].strike_count == 12


def test_a_corpus_standardizes_the_vectors_it_reports(connection: Connection, separable_catalog: SeededCatalog) -> None:
    """A distance over the raw mixture measures a unit choice, so the corpus reads one scale."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    assert np.allclose(corpus.vectors.mean(axis=0), 0.0, atol=1e-9)
    assert np.allclose(corpus.vectors.std(axis=0), 1.0, atol=1e-9)


def test_an_experiment_with_no_vectors_says_so(connection: Connection, separable_catalog: SeededCatalog) -> None:
    with pytest.raises(ValueError, match="holds no feature vectors"):
        load_corpus(connection, experiment_id=separable_catalog.experiment_id + 1)


def test_every_sample_stands_as_its_own_class_while_no_relations_are_recorded(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Grouping is correct to apply from the start, and changes nothing until links exist."""
    groups = equivalence_groups(connection, separable_catalog.sample_hashes)

    assert len(set(groups.tolist())) == len(separable_catalog.sample_hashes)


def test_a_corpus_whose_arrays_disagree_says_so() -> None:
    with pytest.raises(ValueError, match="every array must name the same samples"):
        EvaluationCorpus(
            sample_hashes=("a" * 64, "b" * 64),
            vectors=np.zeros((2, 3)),
            categories=(SampleCategory.KICK,),
            note_statistics=(None, None),
            equivalence_groups=np.array([0, 1]),
            standardization=Standardization(center=np.zeros(3), scale=np.ones(3)),
        )


def test_a_body_of_noise_leaves_every_sample_categorized_but_unstructured(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=False)

    corpus = load_corpus(connection, experiment_id=catalog.experiment_id)

    assert corpus.categorized.all()
    assert corpus.sample_count == len(catalog.sample_hashes)


def test_linked_samples_share_one_equivalence_class(connection: Connection, separable_catalog: SeededCatalog) -> None:
    """A near-duplicate on both sides of a split would let a descriptor retrieve its own copy."""
    first, second, third = separable_catalog.sample_hashes[:3]
    repository = PostgresSampleRelationRepository(connection)
    for subject, reference in ((first, second), (second, third)):
        repository.upsert(
            SampleRelation(
                id=repository.next_id(),
                subject_hash=min(subject, reference),
                reference_hash=max(subject, reference),
                relation_type=RelationType.RESAMPLED_VARIANT,
                method="test",
                confidence=1.0,
                evidence={},
                detected_at=datetime.now(UTC),
            )
        )

    groups = equivalence_groups(connection, separable_catalog.sample_hashes)

    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[0]
