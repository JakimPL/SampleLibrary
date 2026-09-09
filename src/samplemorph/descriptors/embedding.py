from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.experiment import LEARNED_BACKEND_NAME, MODEL_PARAMETER, SampleFeatureVector
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplemorph.descriptors.learned import LearnedDescriptor
from samplemorph.training.descriptor_cache import GridCache
from samplemorph.training.descriptor_data import STORED_VIEW

EMBEDDING_BATCH_SIZE: Final[int] = 512
INSERT_CHUNK_SIZE: Final[int] = 5_000


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
    if cache.description.geometry != descriptor.description.geometry or (
        cache.description.band_count != descriptor.description.shape.band_count
    ):
        raise ValueError(f"the cache under {cache.directory} was built on a grid this descriptor does not read")

    vectors = []
    with torch.no_grad():
        for start in range(0, cache.sample_count, EMBEDDING_BATCH_SIZE):
            grids = torch.from_numpy(cache.grids[start : start + EMBEDDING_BATCH_SIZE, STORED_VIEW].astype(np.float32))
            durations = torch.from_numpy(cache.durations[start : start + EMBEDDING_BATCH_SIZE, STORED_VIEW])
            described = descriptor.model(grids.to(descriptor.device), durations.to(descriptor.device))
            vectors.append(described.cpu().numpy())
    return np.concatenate(vectors).astype(np.float64)


def embed_cache(
    connection: Connection,
    *,
    descriptor: LearnedDescriptor,
    cache: GridCache,
    model_name: str,
    label: str | None,
) -> EmbeddingSummary:
    """Open an experiment for this descriptor and write every cached sample's vector into it.

    The experiment records the model's name, which is how the cloud's evaluation rebuilds the
    extractor when it needs to describe retuned audio, and how a promotion finds the same vectors.
    """
    vectors = describe_cache(descriptor, cache)
    experiment_id = PostgresExperimentRepository(connection).create(
        backend_name=LEARNED_BACKEND_NAME, label=label, params={MODEL_PARAMETER: model_name}
    )
    repository = PostgresSampleFeatureVectorRepository(connection)
    now = datetime.now(UTC)
    rows = [
        SampleFeatureVector(
            experiment_id=experiment_id,
            sample_hash=sample_hash,
            vector=tuple(float(value) for value in vector),
            computed_at=now,
        )
        for sample_hash, vector in zip(cache.hashes, vectors, strict=True)
    ]
    for start in range(0, len(rows), INSERT_CHUNK_SIZE):
        repository.insert_many(rows[start : start + INSERT_CHUNK_SIZE])
        connection.commit()
    return EmbeddingSummary(experiment_id=experiment_id, sample_count=len(rows))
