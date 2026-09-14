from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.evaluation.settings import EvaluationScope
from samplecloud.standardization import Standardization, fit_standardization
from samplecore.categorization import classify_sample_names
from samplecore.digests import digest_of_rows
from samplecore.labeling.labels import SampleLabel
from samplecore.models.category import SampleCategory
from samplecore.models.note_event import SampleNoteStatistics
from samplecore.naming import NO_SAMPLE_NAMES
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class EvaluationCorpus:
    """One experiment's vectors beside everything a descriptor is scored against.

    The rows line up: index `i` names one sample throughout, so a metric selects the samples it can
    score and reads the same row from every array. Categories reach a tenth of the catalog, note
    statistics reach almost all of it and hand labels reach whatever the person has listened to so
    far, which is why each metric reports its own coverage rather than the harness reporting one.
    """

    scope: EvaluationScope
    sample_hashes: tuple[str, ...]
    vectors: NDArray[np.float64]
    categories: tuple[SampleCategory, ...]
    note_statistics: tuple[SampleNoteStatistics | None, ...]
    labels: tuple[SampleLabel | None, ...]
    equivalence_groups: NDArray[np.int64]
    standardization: Standardization

    def __post_init__(self) -> None:
        counts = {
            "vectors": self.vectors.shape[0],
            "categories": len(self.categories),
            "note statistics": len(self.note_statistics),
            "labels": len(self.labels),
            "equivalence groups": int(self.equivalence_groups.shape[0]),
        }
        mismatched = {name: count for name, count in counts.items() if count != len(self.sample_hashes)}
        if mismatched:
            raise ValueError(
                f"an evaluation corpus of {len(self.sample_hashes)} samples carries {mismatched}, "
                "and every array must name the same samples in the same order"
            )

    @property
    def sample_count(self) -> int:
        return len(self.sample_hashes)

    @property
    def membership_digest(self) -> str:
        """One digest over the samples scored, so two passes can tell they read one corpus."""
        return digest_of_rows((sample_hash,) for sample_hash in self.sample_hashes)

    @property
    def categorized(self) -> NDArray[np.bool_]:
        """Which samples a keyword matched, which is what a category metric can be scored over."""
        return np.array([category is not SampleCategory.UNCATEGORIZED for category in self.categories])

    @property
    def note_reached(self) -> NDArray[np.bool_]:
        """Which samples the note events reach, which is what a note metric can be scored over."""
        return np.array([statistics is not None for statistics in self.note_statistics])

    @property
    def labeled(self) -> NDArray[np.bool_]:
        """Which samples a person labeled, which is what a hand-label metric can be scored over."""
        return np.array([label is not None for label in self.labels])


def load_corpus(connection: Connection, *, experiment_id: int, scope: EvaluationScope) -> EvaluationCorpus:
    """Read one experiment's feature vectors within the scope and every target the catalog can score them against.

    Vectors arrive standardized, on the same definition the promoted cloud's projection is fitted
    from, so a distance here and a distance there describe one space. The standardization is fitted
    over the scoped vectors alone, so a scope reads the same numbers whatever lies outside it.

    Raises:
        ValueError: the experiment holds no feature vectors within the scope, leaving nothing to score.
    """
    feature_vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    match scope:
        case EvaluationScope.CATALOG:
            pass
        case EvaluationScope.MODULES:
            held = PostgresSampleRepository(connection).hashes_held_by_modules()
            feature_vectors = tuple(vector for vector in feature_vectors if vector.sample_hash in held)
    if not feature_vectors:
        raise ValueError(
            f"experiment {experiment_id} holds no feature vectors within the {scope.value} scope, "
            "so there is nothing to evaluate"
        )

    sample_hashes = tuple(vector.sample_hash for vector in feature_vectors)
    raw = np.stack([np.array(vector.vector, dtype=np.float64) for vector in feature_vectors])
    standardization = fit_standardization(raw)
    statistics_by_hash = PostgresNoteEventRepository(connection).note_statistics_for_every_sample()
    categories = _categories_for(connection, sample_hashes)
    return EvaluationCorpus(
        scope=scope,
        sample_hashes=sample_hashes,
        vectors=standardization.apply(raw),
        categories=categories,
        note_statistics=tuple(statistics_by_hash.get(sample_hash) for sample_hash in sample_hashes),
        labels=_labels_for(connection, sample_hashes),
        equivalence_groups=equivalence_groups(connection, sample_hashes),
        standardization=standardization,
    )


def _categories_for(connection: Connection, sample_hashes: tuple[str, ...]) -> tuple[SampleCategory, ...]:
    """Classify every sample from every name it goes by: its own, its instruments' and its folders'."""
    names_by_hash, _ = PostgresSampleRepository(connection).names_and_rates_by_hash(list(sample_hashes))
    return tuple(
        classify_sample_names(names_by_hash.get(sample_hash, NO_SAMPLE_NAMES)) for sample_hash in sample_hashes
    )


def _labels_for(connection: Connection, sample_hashes: tuple[str, ...]) -> tuple[SampleLabel | None, ...]:
    """The label a person gave each sample, read from the curation schema and never written back."""
    annotations = PostgresSampleAnnotationRepository(connection).annotations_by_hash(list(sample_hashes))
    labels: list[SampleLabel | None] = []
    for sample_hash in sample_hashes:
        annotation = annotations.get(sample_hash)
        labels.append(SampleLabel.parse(annotation.label) if annotation is not None and annotation.label else None)
    return tuple(labels)


def equivalence_groups(connection: Connection, sample_hashes: tuple[str, ...]) -> NDArray[np.int64]:
    """Which equivalence class each sample belongs to, so a split keeps a class on one side.

    Two samples the catalog links as near-duplicates would otherwise land on both sides of a split,
    and a nearest-neighbor score would then read a sample's own copy as a successful retrieval. With
    no links recorded, every sample stands as its own class and grouping changes nothing, which is
    what makes this correct to apply from the start.
    """
    position_by_hash = {sample_hash: position for position, sample_hash in enumerate(sample_hashes)}
    parents = list(range(len(sample_hashes)))

    def representative(position: int) -> int:
        while parents[position] != position:
            parents[position] = parents[parents[position]]
            position = parents[position]
        return position

    for relation in PostgresSampleRelationRepository(connection).list_all():
        subject = position_by_hash.get(relation.subject_hash)
        related = position_by_hash.get(relation.reference_hash)
        if subject is not None and related is not None:
            parents[representative(subject)] = representative(related)

    return np.array([representative(position) for position in range(len(sample_hashes))], dtype=np.int64)
