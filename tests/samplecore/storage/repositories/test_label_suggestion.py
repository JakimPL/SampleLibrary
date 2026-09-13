from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy import Connection

from samplecore.models.experiment import ZERO_SHOT_BACKEND_NAME, Experiment
from samplecore.models.label_suggestion import SampleLabelSuggestion
from samplecore.models.sample import Sample
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository


def _create_experiment(connection: Connection) -> int:
    repository = PostgresExperimentRepository(connection)
    experiment_id = repository.next_id()
    repository.insert(
        Experiment(
            id=experiment_id, backend_name=ZERO_SHOT_BACKEND_NAME, params={}, created_at=datetime.now(UTC), label=None
        )
    )
    return experiment_id


def _suggestion(experiment_id: int, sample_hash: str, *, rank: int, label: str, score: float) -> SampleLabelSuggestion:
    return SampleLabelSuggestion(
        experiment_id=experiment_id,
        sample_hash=sample_hash,
        rank=rank,
        label=label,
        score=score,
        computed_at=datetime.now(UTC),
    )


def test_an_empty_table_holds_no_scoring(connection: Connection) -> None:
    repository = PostgresSampleLabelSuggestionRepository(connection)

    assert repository.latest_experiment_id() is None
    assert repository.list_for_experiment(_create_experiment(connection)) == ()


def test_insert_many_with_no_suggestions_is_a_no_op(connection: Connection) -> None:
    PostgresSampleLabelSuggestionRepository(connection).insert_many([])


def test_a_samples_suggestions_come_back_in_rank_order(connection: Connection, stored_sample: Sample) -> None:
    experiment_id = _create_experiment(connection)
    second = _suggestion(experiment_id, stored_sample.hash, rank=1, label="SNARE", score=0.4)
    first = _suggestion(experiment_id, stored_sample.hash, rank=0, label="BASS DRUM: KICK", score=0.7)
    repository = PostgresSampleLabelSuggestionRepository(connection)

    repository.insert_many([second, first])

    assert repository.list_for_experiment(experiment_id) == (first, second)
    assert repository.get_many(experiment_id, [stored_sample.hash, "f" * 64]) == {stored_sample.hash: (first, second)}


def test_the_latest_scoring_is_the_experiment_with_the_highest_id(
    connection: Connection, stored_sample: Sample
) -> None:
    earlier = _create_experiment(connection)
    later = _create_experiment(connection)
    repository = PostgresSampleLabelSuggestionRepository(connection)
    repository.insert_many([_suggestion(later, stored_sample.hash, rank=0, label="PIANO", score=0.5)])
    repository.insert_many([_suggestion(earlier, stored_sample.hash, rank=0, label="STRINGS", score=0.6)])

    assert repository.latest_experiment_id() == later
    assert [suggestion.label for suggestion in repository.list_for_experiment(earlier)] == ["STRINGS"]


def test_a_suggestion_for_an_uncataloged_sample_is_refused(connection: Connection) -> None:
    experiment_id = _create_experiment(connection)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        PostgresSampleLabelSuggestionRepository(connection).insert_many(
            [_suggestion(experiment_id, "f" * 64, rank=0, label="PIANO", score=0.5)]
        )


def test_first_pick_counts_count_each_label_s_first_picks_where_the_rows_are(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    experiment_id = _create_experiment(connection)
    repository = PostgresSampleLabelSuggestionRepository(connection)
    repository.insert_many(
        [
            _suggestion(experiment_id, stored_sample.hash, rank=0, label="SNARE", score=0.9),
            _suggestion(experiment_id, stored_sample.hash, rank=1, label="CLAP", score=0.4),
            _suggestion(experiment_id, stored_sample_b.hash, rank=0, label="SNARE", score=0.8),
        ]
    )

    assert repository.first_pick_counts(experiment_id) == {"SNARE": 2}
    assert repository.first_pick_counts(_create_experiment(connection)) == {}
