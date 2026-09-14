from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.suggestions.vocabulary import PROMPT_TEMPLATE
from samplecore.labeling.labels import SampleLabel, written_paths
from samplecore.models.experiment import VOCABULARY_PARAMETER, ZERO_SHOT_BACKEND_NAME, Experiment
from samplecore.models.label_suggestion import SampleLabelSuggestion
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

DEFAULT_SUGGESTION_COUNT: Final[int] = 3
MINIMUM_SUGGESTION_COUNT: Final[int] = 1
MAXIMUM_SUGGESTION_COUNT: Final[int] = 256
INSERT_CHUNK_SAMPLES: Final[int] = 2_000
SOURCE_EXPERIMENT_PARAMETER: Final[str] = "source_experiment_id"
CHECKPOINT_PARAMETER: Final[str] = "checkpoint"
TEMPLATE_PARAMETER: Final[str] = "template"
SUGGESTION_COUNT_PARAMETER: Final[str] = "top"


@dataclass(frozen=True)
class ScoringRecipe:
    """What one scoring is made of: whose vectors, which words, how many kept, and under which name."""

    source_experiment_id: int
    checkpoint: str
    vocabulary: tuple[str, ...]
    suggestion_count: int
    label: str | None

    def __post_init__(self) -> None:
        if not MINIMUM_SUGGESTION_COUNT <= self.suggestion_count <= MAXIMUM_SUGGESTION_COUNT:
            raise ValueError(
                f"a sample keeps between {MINIMUM_SUGGESTION_COUNT} and {MAXIMUM_SUGGESTION_COUNT} suggestions, "
                f"got {self.suggestion_count}"
            )
        if not self.vocabulary:
            raise ValueError("a scoring ranks at least one label")

    def parameters(self) -> dict[str, Any]:
        return {
            SOURCE_EXPERIMENT_PARAMETER: self.source_experiment_id,
            CHECKPOINT_PARAMETER: self.checkpoint,
            TEMPLATE_PARAMETER: PROMPT_TEMPLATE,
            VOCABULARY_PARAMETER: list(self.vocabulary),
            SUGGESTION_COUNT_PARAMETER: self.suggestion_count,
        }


@dataclass(frozen=True)
class HandLabelAgreement:
    """How the first suggestion agrees with what a person wrote, over the samples a person labeled.

    An exact agreement is a suggestion the person asserted as written, its category included; a
    category agreement is one whose category the person asserted, whatever they specified under it.
    """

    labeled: int
    exact: int
    category: int


@dataclass(frozen=True)
class ScoringSummary:
    """What one scoring wrote: its experiment, how many samples it reached, and how its picks read."""

    experiment_id: int
    sample_count: int
    first_picks: dict[str, int]
    agreement: HandLabelAgreement


def score_suggestions(connection: Connection, *, recipe: ScoringRecipe, prompts: NDArray[np.float32]) -> ScoringSummary:
    """Rank the vocabulary for every vector of the source experiment and store the closest labels.

    Both the stored audio vectors and the prompt vectors are unit length, so one matrix product
    reads every cosine at once; the top `suggestion_count` labels of each sample are written
    under a new experiment. The experiment and every suggestion land in one transaction, so a
    reader sees a scoring whole or sees none of it.

    Raises:
        ValueError: the source experiment holds no vectors to score.
    """
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(recipe.source_experiment_id)
    if not vectors:
        raise ValueError(f"experiment {recipe.source_experiment_id} holds no vectors to score")

    # (samples, embedding size) against (labels, embedding size): one cosine per sample and label
    matrix = np.stack([np.asarray(vector.vector, dtype=np.float32) for vector in vectors])
    scores = matrix @ prompts.T
    kept = min(recipe.suggestion_count, len(recipe.vocabulary))
    order = np.argsort(-scores, axis=1)[:, :kept]
    computed_at = datetime.now(UTC)
    with start_batch(connection):
        experiments = PostgresExperimentRepository(connection)
        experiment_id = experiments.next_id()
        experiments.insert(
            Experiment(
                id=experiment_id,
                backend_name=ZERO_SHOT_BACKEND_NAME,
                params=recipe.parameters(),
                created_at=computed_at,
                label=recipe.label,
            )
        )
        repository = PostgresSampleLabelSuggestionRepository(connection)
        for chunk_start in range(0, len(vectors), INSERT_CHUNK_SAMPLES):
            repository.insert_many(
                [
                    SampleLabelSuggestion(
                        experiment_id=experiment_id,
                        sample_hash=vectors[row].sample_hash,
                        rank=rank,
                        label=recipe.vocabulary[index],
                        score=float(scores[row, index]),
                        computed_at=computed_at,
                    )
                    for row in range(chunk_start, min(chunk_start + INSERT_CHUNK_SAMPLES, len(vectors)))
                    for rank, index in enumerate(order[row])
                ]
            )

    first_pick_by_hash = {vector.sample_hash: recipe.vocabulary[order[row, 0]] for row, vector in enumerate(vectors)}
    return ScoringSummary(
        experiment_id=experiment_id,
        sample_count=len(vectors),
        first_picks=dict(Counter(first_pick_by_hash.values())),
        agreement=hand_label_agreement(connection, first_pick_by_hash),
    )


def hand_label_agreement(connection: Connection, first_pick_by_hash: dict[str, str]) -> HandLabelAgreement:
    """Read the first picks against the hand labels of the samples that carry one."""
    annotations = PostgresSampleAnnotationRepository(connection).annotations_by_hash(list(first_pick_by_hash))
    labeled = exact = category = 0
    for sample_hash, annotation in annotations.items():
        if annotation.label is None:
            continue
        labeled += 1
        closure = SampleLabel.parse(annotation.label).closure
        path, *_ = written_paths(first_pick_by_hash[sample_hash])
        exact += path in closure
        category += path[:1] in closure
    return HandLabelAgreement(labeled=labeled, exact=exact, category=category)
