from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy import Connection

from samplecore.models.experiment import ZERO_SHOT_BACKEND_NAME, Experiment
from samplecore.models.sample import Sample
from samplecore.models.sample_category import CategoryPromotion, SampleCategory
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.sample_category import (
    PostgresCategoryPromotionRepository,
    PostgresSampleCategoryRepository,
)


def _create_experiment(connection: Connection) -> int:
    repository = PostgresExperimentRepository(connection)
    experiment_id = repository.next_id()
    repository.insert(
        Experiment(
            id=experiment_id, backend_name=ZERO_SHOT_BACKEND_NAME, params={}, created_at=datetime.now(UTC), label=None
        )
    )
    return experiment_id


def _category(experiment_id: int, sample_hash: str, *, rank: int, label: str, score: float) -> SampleCategory:
    return SampleCategory(
        experiment_id=experiment_id,
        sample_hash=sample_hash,
        rank=rank,
        label=label,
        score=score,
        computed_at=datetime.now(UTC),
    )


def test_an_empty_table_holds_no_scoring(connection: Connection) -> None:
    repository = PostgresSampleCategoryRepository(connection)

    assert repository.shown_experiment_id() is None
    assert repository.list_for_experiment(_create_experiment(connection)) == ()


def test_insert_many_with_no_categories_is_a_no_op(connection: Connection) -> None:
    PostgresSampleCategoryRepository(connection).insert_many([])


def test_a_samples_categories_come_back_in_rank_order(connection: Connection, stored_sample: Sample) -> None:
    experiment_id = _create_experiment(connection)
    second = _category(experiment_id, stored_sample.hash, rank=1, label="SNARE", score=0.4)
    first = _category(experiment_id, stored_sample.hash, rank=0, label="BASS DRUM: KICK", score=0.7)
    repository = PostgresSampleCategoryRepository(connection)

    repository.insert_many([second, first])

    assert repository.list_for_experiment(experiment_id) == (first, second)
    assert repository.get_many(experiment_id, [stored_sample.hash, "f" * 64]) == {stored_sample.hash: (first, second)}


def test_the_shown_scoring_is_the_one_promoted_last_whatever_its_id(
    connection: Connection, stored_sample: Sample
) -> None:
    earlier = _create_experiment(connection)
    later = _create_experiment(connection)
    repository = PostgresSampleCategoryRepository(connection)
    promotions = PostgresCategoryPromotionRepository(connection)
    repository.insert_many([_category(later, stored_sample.hash, rank=0, label="PIANO", score=0.5)])
    repository.insert_many([_category(earlier, stored_sample.hash, rank=0, label="STRINGS", score=0.6)])

    promotions.record(CategoryPromotion(experiment_id=later, promoted_at=datetime.now(UTC)))
    assert repository.shown_experiment_id() == later
    promotions.record(CategoryPromotion(experiment_id=earlier, promoted_at=datetime.now(UTC)))
    assert repository.shown_experiment_id() == earlier
    assert [category.label for category in repository.list_for_experiment(earlier)] == ["STRINGS"]


def test_a_category_for_an_uncataloged_sample_is_refused(connection: Connection) -> None:
    experiment_id = _create_experiment(connection)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        PostgresSampleCategoryRepository(connection).insert_many(
            [_category(experiment_id, "f" * 64, rank=0, label="PIANO", score=0.5)]
        )


def test_first_pick_labels_name_the_closest_label_of_each_sample_the_scoring_reached(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    experiment_id = _create_experiment(connection)
    other_experiment_id = _create_experiment(connection)
    repository = PostgresSampleCategoryRepository(connection)
    repository.insert_many(
        [
            _category(experiment_id, stored_sample.hash, rank=1, label="CLAP", score=0.4),
            _category(experiment_id, stored_sample.hash, rank=0, label="SNARE", score=0.9),
            _category(other_experiment_id, stored_sample_b.hash, rank=0, label="PIANO", score=0.6),
        ]
    )

    labels = repository.top_category_labels(experiment_id, [stored_sample.hash, stored_sample_b.hash])

    assert labels == {stored_sample.hash: "SNARE"}
    assert repository.top_category_labels(experiment_id, []) == {}


def test_first_pick_counts_count_each_label_s_first_picks_where_the_rows_are(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    experiment_id = _create_experiment(connection)
    repository = PostgresSampleCategoryRepository(connection)
    repository.insert_many(
        [
            _category(experiment_id, stored_sample.hash, rank=0, label="SNARE", score=0.9),
            _category(experiment_id, stored_sample.hash, rank=1, label="CLAP", score=0.4),
            _category(experiment_id, stored_sample_b.hash, rank=0, label="SNARE", score=0.8),
        ]
    )

    assert repository.top_category_counts(experiment_id) == {"SNARE": 2}
    assert repository.top_category_counts(_create_experiment(connection)) == {}
