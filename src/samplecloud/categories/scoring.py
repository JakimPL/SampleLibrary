from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.categories.vocabulary import PROMPT_TEMPLATE
from samplecore.labeling.labels import SampleLabel, written_paths
from samplecore.models.experiment import (
    CHECKPOINT_REVISION_PARAMETER,
    VOCABULARY_PARAMETER,
    ZERO_SHOT_BACKEND_NAME,
    Experiment,
    ExperimentKey,
)
from samplecore.models.label_suggestion import SampleLabelSuggestion, SuggestionPromotion
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.label_suggestion import (
    PostgresSampleLabelSuggestionRepository,
    PostgresSuggestionPromotionRepository,
)
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

DEFAULT_CATEGORY_COUNT: Final[int] = 3
MINIMUM_CATEGORY_COUNT: Final[int] = 1
MAXIMUM_CATEGORY_COUNT: Final[int] = 256
INSERT_CHUNK_SAMPLES: Final[int] = 2_000
SOURCE_EXPERIMENT_PARAMETER: Final[str] = "source_experiment_id"
CHECKPOINT_PARAMETER: Final[str] = "checkpoint"
TEMPLATE_PARAMETER: Final[str] = "template"
CATEGORY_COUNT_PARAMETER: Final[str] = "top"


class ScoringConflict(ValueError):
    """Raised when a key names a scoring made from other vectors, words or counts than a request asks for."""


@dataclass(frozen=True)
class ScoringRecipe:
    """What one scoring is made of: whose vectors, which words, how many kept, under which label, and the key it is filed under."""

    source_experiment_id: int
    checkpoint: str
    checkpoint_revision: str
    vocabulary: tuple[str, ...]
    category_count: int
    label: str | None
    key: ExperimentKey | None

    def __post_init__(self) -> None:
        if not MINIMUM_CATEGORY_COUNT <= self.category_count <= MAXIMUM_CATEGORY_COUNT:
            raise ValueError(
                f"a sample keeps between {MINIMUM_CATEGORY_COUNT} and {MAXIMUM_CATEGORY_COUNT} categories, "
                f"got {self.category_count}"
            )
        if not self.vocabulary:
            raise ValueError("a scoring ranks at least one label")

    def parameters(self) -> dict[str, Any]:
        return {
            SOURCE_EXPERIMENT_PARAMETER: self.source_experiment_id,
            CHECKPOINT_PARAMETER: self.checkpoint,
            CHECKPOINT_REVISION_PARAMETER: self.checkpoint_revision,
            TEMPLATE_PARAMETER: PROMPT_TEMPLATE,
            VOCABULARY_PARAMETER: list(self.vocabulary),
            CATEGORY_COUNT_PARAMETER: self.category_count,
        }


@dataclass(frozen=True)
class HandLabelAgreement:
    """How the top category agrees with what a person wrote, over the samples a person labeled.

    An exact agreement is a category the person asserted as written, its top level included; a
    top-level agreement is one whose top level the person asserted, whatever they specified under it.
    """

    labeled: int
    exact: int
    top_level: int


@dataclass(frozen=True)
class ScoringSummary:
    """What one scoring wrote: its experiment, how many samples it reached, and how its picks read."""

    experiment_id: int
    sample_count: int
    top_category_counts: dict[str, int]
    agreement: HandLabelAgreement


def score_categories(connection: Connection, *, recipe: ScoringRecipe, prompts: NDArray[np.float32]) -> ScoringSummary:
    """Rank the vocabulary for every vector of the source experiment and store the closest labels.

    Both the stored audio vectors and the prompt vectors are unit length, so one matrix product
    reads every cosine at once; the top `category_count` labels of each sample are written
    under a new experiment. The experiment, every category and the record that the application
    shows this scoring land in one transaction, so a reader sees a scoring whole or sees none of it.

    Raises:
        ValueError: the source experiment holds no vectors to score.
    """
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(recipe.source_experiment_id)
    if not vectors:
        raise ValueError(f"experiment {recipe.source_experiment_id} holds no vectors to score")

    # (samples, embedding size) against (labels, embedding size): one cosine per sample and label
    matrix = np.stack([np.asarray(vector.vector, dtype=np.float32) for vector in vectors])
    scores = matrix @ prompts.T
    kept = min(recipe.category_count, len(recipe.vocabulary))
    order = np.argsort(-scores, axis=1)[:, :kept]
    computed_at = datetime.now(UTC)
    with start_batch(connection):
        experiment_id = PostgresExperimentRepository(connection).insert_new(
            backend_name=ZERO_SHOT_BACKEND_NAME, label=recipe.label, params=recipe.parameters(), key=recipe.key
        )
        PostgresSuggestionPromotionRepository(connection).record(
            SuggestionPromotion(experiment_id=experiment_id, promoted_at=computed_at)
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

    top_category_by_hash = {vector.sample_hash: recipe.vocabulary[order[row, 0]] for row, vector in enumerate(vectors)}
    return ScoringSummary(
        experiment_id=experiment_id,
        sample_count=len(vectors),
        top_category_counts=dict(Counter(top_category_by_hash.values())),
        agreement=hand_label_agreement(connection, top_category_by_hash),
    )


def filed_scoring(connection: Connection, recipe: ScoringRecipe) -> Experiment | None:
    """The scoring filed under the recipe's key, when an earlier run wrote one, or nothing.

    Raises:
        ScoringConflict: the key names an experiment made some other way than this recipe would make it.
    """
    if recipe.key is None:
        return None
    filed = PostgresExperimentRepository(connection).get_by_key(recipe.key)
    if filed is None:
        return None
    if filed.backend_name != ZERO_SHOT_BACKEND_NAME or filed.params != recipe.parameters():
        raise ScoringConflict(
            f"experiment {filed.id}, filed under {recipe.key}, was made by another recipe than this request names"
        )
    return filed


def show_scoring(connection: Connection, experiment_id: int) -> None:
    """Make a scoring written earlier the one the application shows."""
    with start_batch(connection):
        PostgresSuggestionPromotionRepository(connection).record(
            SuggestionPromotion(experiment_id=experiment_id, promoted_at=datetime.now(UTC))
        )


def hand_label_agreement(connection: Connection, top_category_by_hash: dict[str, str]) -> HandLabelAgreement:
    """Read the top categories against the hand labels of the samples that carry one."""
    annotations = PostgresSampleAnnotationRepository(connection).annotations_by_hash(list(top_category_by_hash))
    labeled = exact = top_level = 0
    for sample_hash, annotation in annotations.items():
        if annotation.label is None:
            continue
        labeled += 1
        closure = SampleLabel.parse(annotation.label).closure
        path, *_ = written_paths(top_category_by_hash[sample_hash])
        exact += path in closure
        top_level += path[:1] in closure
    return HandLabelAgreement(labeled=labeled, exact=exact, top_level=top_level)
