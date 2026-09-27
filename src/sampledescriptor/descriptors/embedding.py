from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.experiment import (
    LEARNED_BACKEND_NAME,
    MODEL_PARAMETER,
    READING_PARAMETER,
    ExperimentKey,
    Reading,
    SampleFeatureVector,
)
from samplecore.progress import ProgressBar
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from sampledescriptor.descriptors.learned import LearnedDescriptor
from sampledescriptor.training.descriptor.cache import STORED_VIEW, GridCache

EMBEDDING_BATCH_SIZE: Final[int] = 512
INSERT_CHUNK_SIZE: Final[int] = 5_000
DESCRIBING_LABEL: Final[str] = "Describing samples"


@dataclass(frozen=True)
class EmbeddingSummary:
    """What one embedding pass wrote: the experiment it opened and how many vectors it holds."""

    experiment_id: int
    sample_count: int


def describe_cache(descriptor: LearnedDescriptor, cache: GridCache) -> NDArray[np.float64]:
    """One vector per cached sample, read from the stored grids the cache already holds.

    The cache pooled every grid the way the descriptor reads it, so describing the catalog costs a
    forward pass over the cache rather than a canonicalization of every waveform again.

    Raises:
        ValueError: the cache was pooled differently from how the descriptor reads.
    """
    return describe_rows(descriptor, cache, np.arange(cache.sample_count))


def describe_rows(descriptor: LearnedDescriptor, cache: GridCache, rows: NDArray[np.intp]) -> NDArray[np.float64]:
    """One vector for each of the cache's `rows`, in the order given, read from their stored grids.

    Raises:
        ValueError: the cache was pooled differently from how the descriptor reads.
    """
    if cache.description.geometry != descriptor.description.geometry or (
        cache.description.band_count != descriptor.description.shape.band_count
    ):
        raise ValueError(f"the cache under {cache.directory} was built on a grid this descriptor does not read")

    vectors = [np.empty((0, descriptor.description.shape.embedding_size), dtype=np.float32)]
    with torch.no_grad():
        for start in range(0, len(rows), EMBEDDING_BATCH_SIZE):
            batch = rows[start : start + EMBEDDING_BATCH_SIZE]
            grids = torch.from_numpy(cache.grids[batch, STORED_VIEW].astype(np.float32))
            durations = torch.from_numpy(np.ascontiguousarray(cache.durations[batch, STORED_VIEW]))
            described = descriptor.model(grids.to(descriptor.device), durations.to(descriptor.device))
            vectors.append(described.cpu().numpy())
    return np.concatenate(vectors).astype(np.float64)


@dataclass(frozen=True)
class EmbeddingFiling:
    """How the experiment an embedding opens is recorded: the stored model it names, a note, and the key it is filed under."""

    model_name: str
    label: str | None
    key: ExperimentKey | None


def embed_cache(
    connection: Connection, *, descriptor: LearnedDescriptor, cache: GridCache, filing: EmbeddingFiling
) -> EmbeddingSummary:
    """Write every cached sample's vector into this descriptor's experiment, opening it where the key names none.

    The experiment records the model's name and the nominal reading its grids were cached under,
    which is how the cloud's evaluation rebuilds the extractor when it needs to describe retuned
    audio, and how resuming the experiment reads new samples the way these were read. The
    experiment is committed first and the vectors follow `INSERT_CHUNK_SIZE` at a time, each chunk in
    its own transaction, so a pass stopped partway keeps every chunk it wrote, and the next pass
    filing under the same key describes only the samples the experiment still lacks. A key is a
    digest of the descriptor and the cache, so the experiment it names is the one these inputs make.

    Raises:
        ValueError: the cache was pooled differently from how the descriptor reads.
    """
    experiment_id = _experiment_for(connection, filing)
    repository = PostgresSampleFeatureVectorRepository(connection)
    held = repository.sample_hashes_for_experiment(experiment_id)
    pending = np.array([row for row, sample_hash in enumerate(cache.hashes) if sample_hash not in held], dtype=np.intp)
    with ProgressBar(
        total=cache.sample_count, label=DESCRIBING_LABEL, resumed=cache.sample_count - len(pending)
    ) as progress:
        for start in range(0, len(pending), INSERT_CHUNK_SIZE):
            rows = pending[start : start + INSERT_CHUNK_SIZE]
            vectors = describe_rows(descriptor, cache, rows)
            now = datetime.now(UTC)
            with start_batch(connection):
                repository.insert_many(
                    [
                        SampleFeatureVector(
                            experiment_id=experiment_id,
                            sample_hash=cache.hashes[row],
                            vector=tuple(float(value) for value in vector),
                            computed_at=now,
                        )
                        for row, vector in zip(rows.tolist(), vectors, strict=True)
                    ]
                )
            progress.update(len(rows))
    return EmbeddingSummary(experiment_id=experiment_id, sample_count=cache.sample_count)


def _experiment_for(connection: Connection, filing: EmbeddingFiling) -> int:
    """The experiment filed under the filing's key, or a new one committed before any vector is written."""
    experiments = PostgresExperimentRepository(connection)
    if filing.key is not None:
        filed = experiments.get_by_key(filing.key)
        if filed is not None:
            return filed.id
    with start_batch(connection):
        return experiments.insert_new(
            backend_name=LEARNED_BACKEND_NAME,
            label=filing.label,
            params={MODEL_PARAMETER: filing.model_name, READING_PARAMETER: Reading.NOMINAL.value},
            key=filing.key,
        )
