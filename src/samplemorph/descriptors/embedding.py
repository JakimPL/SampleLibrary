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
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplemorph.descriptors.learned import LearnedDescriptor
from samplemorph.training.descriptor_cache import STORED_VIEW, GridCache

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


@dataclass(frozen=True)
class EmbeddingFiling:
    """How the experiment an embedding opens is recorded: the stored model it names, a note, and the key it is filed under."""

    model_name: str
    label: str | None
    key: ExperimentKey | None


def embed_cache(
    connection: Connection, *, descriptor: LearnedDescriptor, cache: GridCache, filing: EmbeddingFiling
) -> EmbeddingSummary:
    """Open an experiment for this descriptor and write every cached sample's vector into it.

    The experiment records the model's name and the nominal reading its grids were cached under,
    which is how the cloud's evaluation rebuilds the extractor when it needs to describe retuned
    audio, and how resuming the experiment reads new samples the way these were read. The
    experiment and every vector land in one transaction, so an experiment a key names holds the
    whole cache, and a pass stopped partway leaves the catalog as it was.
    """
    vectors = describe_cache(descriptor, cache)
    now = datetime.now(UTC)
    with start_batch(connection):
        experiment_id = PostgresExperimentRepository(connection).insert_new(
            backend_name=LEARNED_BACKEND_NAME,
            label=filing.label,
            params={MODEL_PARAMETER: filing.model_name, READING_PARAMETER: Reading.NOMINAL.value},
            key=filing.key,
        )
        repository = PostgresSampleFeatureVectorRepository(connection)
        for start in range(0, len(cache.hashes), INSERT_CHUNK_SIZE):
            repository.insert_many(
                [
                    SampleFeatureVector(
                        experiment_id=experiment_id,
                        sample_hash=sample_hash,
                        vector=tuple(float(value) for value in vector),
                        computed_at=now,
                    )
                    for sample_hash, vector in zip(
                        cache.hashes[start : start + INSERT_CHUNK_SIZE],
                        vectors[start : start + INSERT_CHUNK_SIZE],
                        strict=True,
                    )
                ]
            )
    return EmbeddingSummary(experiment_id=experiment_id, sample_count=len(cache.hashes))
