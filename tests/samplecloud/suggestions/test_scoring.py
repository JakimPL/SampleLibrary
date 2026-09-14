from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import Connection, func, select
from trackmod.core.samples.depth import BitDepth

from samplecloud.backends.teacher_backend import TEACHER_BACKEND_NAME, TEACHER_EMBEDDING_SIZE
from samplecloud.suggestions.scoring import (
    MAXIMUM_SUGGESTION_COUNT,
    HandLabelAgreement,
    ScoringRecipe,
    score_suggestions,
)
from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import ZERO_SHOT_BACKEND_NAME, SampleFeatureVector
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.database import experiment
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

VOCABULARY = ("BASS DRUM", "SNARE", "HI-HAT: CLOSED")
KICK_HASH = "a" * 64
HAT_HASH = "b" * 64


def seed_listening_experiment(connection: Connection) -> int:
    """Two samples whose vectors point straight at the first and the third label of the vocabulary."""
    samples = PostgresSampleRepository(connection)
    vectors = []
    for sample_hash, position in ((KICK_HASH, 0), (HAT_HASH, 2)):
        samples.upsert(Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32))
        vector = np.zeros(TEACHER_EMBEDDING_SIZE)
        vector[position] = 1.0
        vectors.append(
            SampleFeatureVector(
                experiment_id=0, sample_hash=sample_hash, vector=tuple(vector.tolist()), computed_at=datetime.now(UTC)
            )
        )
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name=TEACHER_BACKEND_NAME, label="stub listening", params={}
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [vector.model_copy(update={"experiment_id": experiment_id}) for vector in vectors]
    )
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            _annotation(KICK_HASH, "BASS DRUM: KICK"),
            _annotation(HAT_HASH, "SNARE"),
        )
    )
    connection.commit()
    return experiment_id


def prompts() -> np.ndarray:
    return np.eye(len(VOCABULARY), TEACHER_EMBEDDING_SIZE, dtype=np.float32)


def test_each_sample_keeps_its_closest_labels_first_under_a_new_experiment(connection: Connection) -> None:
    source = seed_listening_experiment(connection)

    summary = score_suggestions(
        connection,
        recipe=ScoringRecipe(
            source_experiment_id=source, checkpoint="stub", vocabulary=VOCABULARY, suggestion_count=2, label=None
        ),
        prompts=prompts(),
    )

    repository = PostgresSampleLabelSuggestionRepository(connection)
    suggestions = repository.get_many(summary.experiment_id, [KICK_HASH, HAT_HASH])
    assert [suggestion.label for suggestion in suggestions[KICK_HASH]][0] == "BASS DRUM"
    assert [suggestion.label for suggestion in suggestions[HAT_HASH]][0] == "HI-HAT: CLOSED"
    assert all(len(held) == 2 for held in suggestions.values())
    assert suggestions[KICK_HASH][0].score == pytest.approx(1.0)
    assert repository.latest_experiment_id() == summary.experiment_id
    experiment = PostgresExperimentRepository(connection).get(summary.experiment_id)
    assert experiment is not None
    assert experiment.backend_name == ZERO_SHOT_BACKEND_NAME
    assert experiment.params["vocabulary"] == list(VOCABULARY)
    assert experiment.params["source_experiment_id"] == source


def test_the_summary_counts_the_first_picks_and_their_agreement_with_the_hand_labels(connection: Connection) -> None:
    """The kick's first pick is the category its label specifies; the hat's first pick contradicts its label."""
    source = seed_listening_experiment(connection)

    summary = score_suggestions(
        connection,
        recipe=ScoringRecipe(
            source_experiment_id=source, checkpoint="stub", vocabulary=VOCABULARY, suggestion_count=1, label=None
        ),
        prompts=prompts(),
    )

    assert summary.sample_count == 2
    assert summary.first_picks == {"BASS DRUM": 1, "HI-HAT: CLOSED": 1}
    assert summary.agreement == HandLabelAgreement(labeled=2, exact=1, category=1)


def test_an_experiment_without_vectors_says_so(connection: Connection) -> None:
    empty = PostgresExperimentRepository(connection).create(backend_name=TEACHER_BACKEND_NAME, label=None, params={})

    with pytest.raises(ValueError, match="holds no vectors"):
        score_suggestions(
            connection,
            recipe=ScoringRecipe(
                source_experiment_id=empty, checkpoint="stub", vocabulary=VOCABULARY, suggestion_count=1, label=None
            ),
            prompts=prompts(),
        )


def _annotation(sample_hash: str, label: str) -> SampleAnnotation:
    return SampleAnnotation(
        label=label,
        rating=None,
        favorite=False,
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0),
        module_filename="song.xm",
        sample_name="a sample",
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )


def test_a_scoring_interrupted_while_writing_leaves_no_experiment_behind(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader takes the newest scoring as the one to show, so a partial one never becomes visible."""
    source = seed_listening_experiment(connection)
    experiment_count_before = connection.execute(select(func.count()).select_from(experiment)).scalar_one()

    def failing_insert(self: PostgresSampleLabelSuggestionRepository, suggestions: object) -> None:
        raise OSError("simulated failure")

    monkeypatch.setattr(PostgresSampleLabelSuggestionRepository, "insert_many", failing_insert)

    with pytest.raises(OSError, match="simulated failure"):
        score_suggestions(
            connection,
            recipe=ScoringRecipe(
                source_experiment_id=source, checkpoint="stub", vocabulary=VOCABULARY, suggestion_count=1, label=None
            ),
            prompts=prompts(),
        )

    assert connection.execute(select(func.count()).select_from(experiment)).scalar_one() == experiment_count_before
    assert PostgresSampleLabelSuggestionRepository(connection).latest_experiment_id() is None


@pytest.mark.parametrize(
    ("suggestion_count", "vocabulary"),
    [(0, VOCABULARY), (MAXIMUM_SUGGESTION_COUNT + 1, VOCABULARY), (1, ())],
    ids=("no suggestion", "past the bound", "no label to rank"),
)
def test_a_recipe_outside_its_bounds_is_refused(suggestion_count: int, vocabulary: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="at least one label|between"):
        ScoringRecipe(
            source_experiment_id=1,
            checkpoint="stub",
            vocabulary=vocabulary,
            suggestion_count=suggestion_count,
            label=None,
        )
