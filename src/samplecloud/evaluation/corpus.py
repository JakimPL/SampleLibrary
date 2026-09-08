from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.standardization import Standardization, fit_standardization
from samplecore.categorization import classify_sample_category
from samplecore.models.category import SampleCategory
from samplecore.models.note_event import SampleNoteStatistics
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository


@dataclass(frozen=True)
class EvaluationCorpus:
    """One experiment's vectors beside everything a descriptor is scored against.

    The rows line up: index `i` names one sample throughout, so a metric selects the samples it can
    score and reads the same row from every array. Categories reach a tenth of the catalog and note
    statistics reach almost all of it, which is why each metric reports its own coverage rather than
    the harness reporting one.
    """

    sample_hashes: tuple[str, ...]
    vectors: NDArray[np.float64]
    categories: tuple[SampleCategory, ...]
    note_statistics: tuple[SampleNoteStatistics | None, ...]
    equivalence_groups: NDArray[np.int64]
    standardization: Standardization

    def __post_init__(self) -> None:
        counts = {
            "vectors": self.vectors.shape[0],
            "categories": len(self.categories),
            "note statistics": len(self.note_statistics),
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
    def categorized(self) -> NDArray[np.bool_]:
        """Which samples a keyword matched, which is what a category metric can be scored over."""
        return np.array([category is not SampleCategory.UNCATEGORIZED for category in self.categories])

    @property
    def note_reached(self) -> NDArray[np.bool_]:
        """Which samples the note events reach, which is what a note metric can be scored over."""
        return np.array([statistics is not None for statistics in self.note_statistics])


def load_corpus(connection: Connection, *, experiment_id: int) -> EvaluationCorpus:
    """Read one experiment's feature vectors and every target the catalog can score them against.

    Vectors arrive standardized, on the same definition the promoted cloud's projection is fitted
    from, so a distance here and a distance there describe one space.

    Raises:
        ValueError: the experiment holds no feature vectors, leaving nothing to score.
    """
    feature_vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(experiment_id)
    if not feature_vectors:
        raise ValueError(f"experiment {experiment_id} holds no feature vectors, so there is nothing to evaluate")

    sample_hashes = tuple(vector.sample_hash for vector in feature_vectors)
    raw = np.stack([np.array(vector.vector, dtype=np.float64) for vector in feature_vectors])
    standardization = fit_standardization(raw)
    statistics_by_hash = PostgresNoteEventRepository(connection).note_statistics_for_every_sample()
    categories = _categories_for(connection, sample_hashes)
    return EvaluationCorpus(
        sample_hashes=sample_hashes,
        vectors=standardization.apply(raw),
        categories=categories,
        note_statistics=tuple(statistics_by_hash.get(sample_hash) for sample_hash in sample_hashes),
        equivalence_groups=equivalence_groups(connection, sample_hashes),
        standardization=standardization,
    )


def _categories_for(connection: Connection, sample_hashes: tuple[str, ...]) -> tuple[SampleCategory, ...]:
    """Classify every sample from every name it goes by, occurrence names and instrument names alike."""
    repository = PostgresSampleRepository(connection)
    hashes = list(sample_hashes)
    occurrence_names, _ = repository.names_and_rates_by_hash(hashes)
    instrument_names = repository.instrument_names_by_hash(hashes)
    return tuple(
        classify_sample_category(occurrence_names.get(sample_hash, ()) + instrument_names.get(sample_hash, ()))
        for sample_hash in sample_hashes
    )


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
