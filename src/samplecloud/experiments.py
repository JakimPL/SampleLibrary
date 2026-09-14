from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.backends.learned_backend import build_learned_extractor
from samplecloud.hearing import Hearing
from samplecloud.registries import BACKEND_REGISTRY
from samplecore.models.experiment import (
    LEARNED_BACKEND_NAME,
    MODEL_PARAMETER,
    READING_PARAMETER,
    ZERO_SHOT_BACKEND_NAME,
    Experiment,
    Reading,
)
from samplecore.storage import audio_store
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

REPRODUCTION_PROBE_COUNT: Final[int] = 8
REPRODUCTION_MINIMUM_SIMILARITY: Final[float] = 0.999


class ExperimentRefused(ValueError):
    """Raised when a request names an experiment that cannot be embedded, scored or resumed the way it asks."""


class ExtractorChanged(ExperimentRefused):
    """Raised when an experiment's extractor no longer describes its own samples the way it once did."""


@dataclass(frozen=True)
class EmbeddingRecipe:
    """How an experiment's vectors are made: the backend, the reading, and the stored model a learned backend reads."""

    backend_name: str
    reading: Reading
    model_name: str | None

    @property
    def parameters(self) -> dict[str, str]:
        """The recipe in the form an experiment row records it."""
        recorded = {READING_PARAMETER: self.reading.value}
        return recorded | ({MODEL_PARAMETER: self.model_name} if self.model_name is not None else {})


def experiment_named(connection: Connection, experiment_id: int) -> Experiment:
    """The experiment a command names by its id.

    Raises:
        ExperimentRefused: the catalog holds no such experiment.
    """
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    if experiment is None:
        raise ExperimentRefused(f"the catalog holds no experiment {experiment_id}")
    return experiment


def recipe_of(experiment: Experiment) -> EmbeddingRecipe:
    """The recipe an experiment's own row records, which is the one a resumed extraction follows.

    Raises:
        ExperimentRefused: the experiment holds label suggestions rather than vectors, names a backend this
            build lacks, is a learned experiment naming no model, or records no reading.
    """
    if experiment.backend_name == ZERO_SHOT_BACKEND_NAME:
        raise ExperimentRefused(f"experiment {experiment.id} is a scoring of label suggestions, which holds no vectors")
    if experiment.backend_name not in (*BACKEND_REGISTRY, LEARNED_BACKEND_NAME):
        raise ExperimentRefused(
            f"experiment {experiment.id} was made by the {experiment.backend_name} backend, unknown here"
        )

    model_name = experiment.params.get(MODEL_PARAMETER)
    if experiment.backend_name == LEARNED_BACKEND_NAME and not isinstance(model_name, str):
        raise ExperimentRefused(f"experiment {experiment.id} was made by a learned descriptor it does not name")
    reading = experiment.params.get(READING_PARAMETER)
    if reading not in tuple(Reading):
        raise ExperimentRefused(f"experiment {experiment.id} records no reading its samples were heard under")

    return EmbeddingRecipe(
        backend_name=experiment.backend_name,
        reading=Reading(reading),
        model_name=model_name if isinstance(model_name, str) else None,
    )


def extractor_for(recipe: EmbeddingRecipe, *, library_root: Path, device: str) -> FeatureExtractor:
    """The extractor a recipe names, a learned descriptor loaded from the library's model store by its name."""
    if recipe.model_name is not None:
        return build_learned_extractor(library_root, model_name=recipe.model_name, device=device)
    return BACKEND_REGISTRY[recipe.backend_name]()


def require_reproducible(
    connection: Connection, library_root: Path, *, experiment_id: int, extractor: FeatureExtractor, hearing: Hearing
) -> None:
    """Describe a few of an experiment's samples again, and insist the vectors match the ones it holds.

    A learned descriptor is found by name, so retraining it under that name, or a backend changing
    with a library upgrade, would add vectors of another kind to an experiment resumed later. The
    probe is the experiment's first samples in hash order, so every resume checks the same ones.

    Raises:
        ExtractorChanged: a probe sample's new vector points elsewhere than its stored one.
    """
    stored = PostgresSampleFeatureVectorRepository(connection).first_vectors(
        experiment_id, count=REPRODUCTION_PROBE_COUNT
    )
    samples = PostgresSampleRepository(connection).get_many([vector.sample_hash for vector in stored])
    for vector in stored:
        heard = hearing.hear(vector.sample_hash, audio_store.read(library_root, samples[vector.sample_hash]).pcm)
        described = np.asarray(extractor.extract(heard), dtype=np.float64)
        similarity = _cosine(described, np.asarray(vector.vector, dtype=np.float64))
        if similarity < REPRODUCTION_MINIMUM_SIMILARITY:
            raise ExtractorChanged(
                f"experiment {experiment_id}'s extractor now describes sample {vector.sample_hash} at a cosine of "
                f"{similarity:.4f} from the vector it holds, so new vectors would not belong beside the old ones; "
                "start a new experiment instead"
            )


def _cosine(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        return -1.0
    norm = float(np.linalg.norm(first) * np.linalg.norm(second))
    return float(first @ second) / norm if norm > 0.0 else float(np.array_equal(first, second))
