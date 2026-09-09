from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import LEARNED_BACKEND_NAME, MODEL_PARAMETER
from samplecore.models.sample import Sample
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.descriptors.embedding import describe_cache, embed_cache
from samplemorph.descriptors.grid_descriptor import DescriptorShape, GridDescriptor
from samplemorph.descriptors.learned import DescriptorDescription, LearnedDescriptor
from samplemorph.registries import canonicalizer_for_geometry
from samplemorph.training.descriptor_cache import GridCache
from tests.samplemorph.training.conftest import BAND_COUNT, TIME_COLUMNS, write_grid_cache

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

    summary = embed_cache(connection, descriptor=_descriptor(cache), cache=cache, model_name="tiny", label="a test")

    experiment = PostgresExperimentRepository(connection).get(summary.experiment_id)
    assert experiment is not None
    assert experiment.backend_name == LEARNED_BACKEND_NAME
    assert experiment.params == {MODEL_PARAMETER: "tiny"}
    assert experiment.label == "a test"
    vectors = PostgresSampleFeatureVectorRepository(connection).list_for_experiment(summary.experiment_id)
    assert summary.sample_count == len(vectors) == 6
    assert {vector.sample_hash for vector in vectors} == set(cache.hashes)
