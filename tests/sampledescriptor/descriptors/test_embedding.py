from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import (
    LEARNED_BACKEND_NAME,
    MODEL_PARAMETER,
    READING_PARAMETER,
    Reading,
    SampleFeatureVector,
)
from samplecore.models.sample import Sample
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from sampledescriptor.descriptors import embedding
from sampledescriptor.descriptors.embedding import EmbeddingFiling, describe_cache, embed_cache
from sampledescriptor.descriptors.grid_descriptor import GridDescriptor
from sampledescriptor.descriptors.learned import DescriptorDescription, LearnedDescriptor
from sampledescriptor.descriptors.shape import DescriptorShape
from sampledescriptor.registries import canonicalizer_for_geometry
from sampledescriptor.training.descriptor.cache import GridCache
from tests.sampledescriptor.training.conftest import BAND_COUNT, TIME_COLUMNS, write_grid_cache

EMBEDDING_SIZE = 8


def _descriptor(cache: GridCache, *, band_count: int = BAND_COUNT) -> LearnedDescriptor:
    shape = DescriptorShape(
        band_count=band_count, time_columns=TIME_COLUMNS, width=4, stage_count=2, embedding_size=EMBEDDING_SIZE
    )
    description = DescriptorDescription(
        canonicalizer=cache.description.canonicalizer,
        geometry=cache.description.geometry,
        bands_per_semitone=cache.description.bands_per_semitone,
        shape=shape,
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=cache.sample_count,
        best_validation_loss=1.0,
    )
    torch.manual_seed(0)
    return LearnedDescriptor(
        model=GridDescriptor(shape).eval(),
        description=description,
        canonicalizer=canonicalizer_for_geometry(description.geometry),
        device=torch.device("cpu"),
    )


def test_describing_a_cache_reads_every_stored_grid_into_one_unit_vector(tmp_path: Path) -> None:
    cache = write_grid_cache(tmp_path / "cache", sample_count=10)
    descriptor = _descriptor(cache)

    vectors = describe_cache(descriptor, cache)

    assert vectors.shape == (10, EMBEDDING_SIZE)
    assert vectors.dtype == np.float64
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5)
    grid = torch.from_numpy(cache.grids[3, 0].astype(np.float32))[None]
    duration = torch.from_numpy(cache.durations[3:4, 0])
    with torch.no_grad():
        np.testing.assert_allclose(vectors[3], descriptor.model(grid, duration)[0].numpy(), rtol=1e-5)


def test_a_cache_pooled_another_way_is_refused(tmp_path: Path) -> None:
    cache = write_grid_cache(tmp_path / "cache", sample_count=4)

    with pytest.raises(ValueError, match="does not read"):
        describe_cache(_descriptor(cache, band_count=BAND_COUNT * 2), cache)


def test_embedding_a_cache_opens_an_experiment_naming_the_descriptor(connection: Connection, tmp_path: Path) -> None:
    cache = write_grid_cache(tmp_path / "cache", sample_count=6)
    repository = PostgresSampleRepository(connection)
    for sample_hash in cache.hashes:
        repository.upsert(Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4096))
    connection.commit()

    summary = embed_cache(
        connection,
        descriptor=_descriptor(cache),
        cache=cache,
        filing=EmbeddingFiling(model_name="tiny", label="a test", key="learned-tiny"),
    )

    experiment = PostgresExperimentRepository(connection).get(summary.experiment_id)
    assert experiment is not None
    assert experiment.backend_name == LEARNED_BACKEND_NAME
    assert experiment.params == {MODEL_PARAMETER: "tiny", READING_PARAMETER: Reading.NOMINAL.value}
    assert experiment.label == "a test"
    assert experiment.key == "learned-tiny"
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(summary.experiment_id)
    assert summary.sample_count == len(vectors) == 6
    assert {vector.sample_hash for vector in vectors} == set(cache.hashes)


class InsertStopped(RuntimeError):
    pass


def test_an_embedding_stopped_while_writing_keeps_its_chunks_and_a_rerun_describes_the_rest(
    connection: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = write_grid_cache(tmp_path / "cache", sample_count=6)
    repository = PostgresSampleRepository(connection)
    for sample_hash in cache.hashes:
        repository.upsert(Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4096))
    connection.commit()
    descriptor = _descriptor(cache)
    filing = EmbeddingFiling(model_name="tiny", label=None, key="learned-tiny")
    insert_many = PostgresSampleFeatureVectorRepository.insert_many

    def stop_after_the_first_chunk(
        self: PostgresSampleFeatureVectorRepository, vectors: Sequence[SampleFeatureVector]
    ) -> None:
        if PostgresSampleFeatureVectorRepository(connection).list_for_experiment(vectors[0].experiment_id):
            raise InsertStopped("stopped between chunks")
        insert_many(self, vectors)

    monkeypatch.setattr(embedding, "INSERT_CHUNK_SIZE", 2)
    monkeypatch.setattr(PostgresSampleFeatureVectorRepository, "insert_many", stop_after_the_first_chunk)
    with pytest.raises(InsertStopped):
        embed_cache(connection, descriptor=descriptor, cache=cache, filing=filing)
    monkeypatch.setattr(PostgresSampleFeatureVectorRepository, "insert_many", insert_many)
    described: list[int] = []
    describe_rows = embedding.describe_rows

    def counted(*arguments: Any) -> NDArray[np.float64]:
        vectors = describe_rows(*arguments)
        described.append(len(vectors))
        return vectors

    monkeypatch.setattr(embedding, "describe_rows", counted)

    summary = embed_cache(connection, descriptor=descriptor, cache=cache, filing=filing)

    assert sum(described) == 4
    experiments = PostgresExperimentRepository(connection)
    assert experiments.get_by_key("learned-tiny") == experiments.get(summary.experiment_id)
    held = {
        vector.sample_hash: vector.vector
        for vector in PostgresSampleFeatureVectorRepository(connection).list_for_experiment(summary.experiment_id)
    }
    expected = describe_cache(descriptor, cache)
    assert list(held) == sorted(cache.hashes)
    for row, sample_hash in enumerate(cache.hashes):
        np.testing.assert_allclose(held[sample_hash], expected[row], atol=1e-6)
