from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.evaluation.corpus import EvaluationCorpus, equivalence_groups, load_corpus
from samplecloud.evaluation.settings import EvaluationScope
from samplecloud.standardization import Standardization
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import SampleFeatureVector
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from tests.samplecloud.evaluation.conftest import SEEDED_CATEGORIES, SeededCatalog, label_catalog, seed_catalog


def test_a_corpus_carries_one_row_per_feature_vector(connection: Connection, separable_catalog: SeededCatalog) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    assert corpus.sample_count == len(separable_catalog.sample_hashes)
    assert corpus.vectors.shape[0] == corpus.sample_count


def test_a_corpus_reads_how_often_and_how_widely_each_sample_is_played(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    group_by_hash = dict(zip(separable_catalog.sample_hashes, separable_catalog.categories, strict=True))
    statistics = {
        group_by_hash[sample_hash]: entry
        for sample_hash, entry in zip(corpus.sample_hashes, corpus.note_statistics, strict=True)
        if entry is not None
    }
    assert corpus.note_reached.all()
    assert statistics["kick"].distinct_pitch_count == 1
    assert statistics["lead"].distinct_pitch_count == len(SEEDED_CATEGORIES)
    assert statistics["kick"].strike_count == 12


def test_a_corpus_standardizes_the_vectors_it_reports(connection: Connection, separable_catalog: SeededCatalog) -> None:
    """A distance over the raw mixture measures a unit choice, so the corpus reads one scale."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    assert np.allclose(corpus.vectors.mean(axis=0), 0.0, atol=1e-9)
    assert np.allclose(corpus.vectors.std(axis=0), 1.0, atol=1e-9)


def test_an_experiment_with_no_vectors_says_so(connection: Connection, separable_catalog: SeededCatalog) -> None:
    with pytest.raises(ValueError, match="holds no feature vectors"):
        load_corpus(connection, experiment_id=separable_catalog.experiment_id + 1, scope=EvaluationScope.CATALOG)


def test_every_sample_stands_as_its_own_class_while_no_relations_are_recorded(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Grouping is correct to apply from the start, and changes nothing until links exist."""
    groups = equivalence_groups(connection, separable_catalog.sample_hashes)

    assert len(set(groups.tolist())) == len(separable_catalog.sample_hashes)


def test_a_corpus_whose_arrays_disagree_says_so() -> None:
    with pytest.raises(ValueError, match="every array must name the same samples"):
        EvaluationCorpus(
            scope=EvaluationScope.CATALOG,
            sample_hashes=("a" * 64, "b" * 64),
            vectors=np.zeros((2, 3)),
            note_statistics=(None,),
            labels=(None, None),
            equivalence_groups=np.array([0, 1]),
            standardization=Standardization(center=np.zeros(3), scale=np.ones(3)),
        )


def test_a_body_of_noise_is_read_whole(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=False)

    corpus = load_corpus(connection, experiment_id=catalog.experiment_id, scope=EvaluationScope.CATALOG)

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


def test_a_corpus_reads_the_label_a_person_gave_each_sample(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    labeled = label_catalog(connection, separable_catalog, every=2)

    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    assert int(corpus.labeled.sum()) == len(labeled)
    by_hash = dict(zip(corpus.sample_hashes, corpus.labels, strict=True))
    first_kick = by_hash[separable_catalog.sample_hashes[0]]
    assert first_kick is not None
    assert first_kick.paths == {("KICK", "SOFT")}
    assert by_hash[separable_catalog.sample_hashes[1]] is None


def test_the_modules_scope_reads_the_corpus_a_catalog_without_its_sample_files_would(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """A pack sample joining the experiment leaves the modules scope's rows, scaling and digest as they were."""
    before = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)
    pack_sample = "f" * 64
    PostgresSampleRepository(connection).upsert(
        Sample(hash=pack_sample, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=4096)
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=separable_catalog.experiment_id,
                sample_hash=pack_sample,
                vector=tuple(float(value) for value in np.full(before.vectors.shape[1], 50.0)),
                computed_at=datetime.now(UTC),
            )
        ]
    )
    connection.commit()

    catalog = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)
    modules = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.MODULES)

    assert catalog.sample_count == before.sample_count + 1
    assert catalog.membership_digest != before.membership_digest
    assert modules.sample_hashes == before.sample_hashes
    assert modules.membership_digest == before.membership_digest
    np.testing.assert_allclose(modules.vectors, before.vectors)


def test_an_experiment_describing_no_module_sample_has_nothing_to_score_in_the_modules_scope(
    connection: Connection, tmp_path: Path
) -> None:
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name="stub", label=None, params={}, key=None
    )
    PostgresSampleRepository(connection).upsert(
        Sample(hash="e" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.STEREO, frames=4096)
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=experiment_id, sample_hash="e" * 64, vector=(1.0, 0.0), computed_at=datetime.now(UTC)
            )
        ]
    )
    connection.commit()

    with pytest.raises(ValueError, match="within the modules scope"):
        load_corpus(connection, experiment_id=experiment_id, scope=EvaluationScope.MODULES)
