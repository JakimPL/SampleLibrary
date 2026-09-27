from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pytest
from scipy.spatial.distance import cdist, pdist
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.modules import distance as distance_module
from samplecloud.modules import run as run_module
from samplecloud.modules.run import lay_out_and_persist_modules
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import MODSampleProperties, SampleOccurrence
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.cloud import PostgresModuleCloudCoordinateRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository

SAMPLES_PER_GROUP: Final[int] = 6
MODULES_PER_GROUP: Final[int] = 5
SAMPLES_PER_MODULE: Final[int] = 3
DIMENSIONS: Final[int] = 4
GROUP_OFFSET: Final[float] = 40.0


@pytest.fixture
def library_root(tmp_path: Path) -> Path:
    return tmp_path / "library"


def _sample_hash(index: int) -> str:
    return format(index + 1, "064x")


def _module_hash(index: int) -> str:
    return format(index + 1, "064x").replace("0", "e")


def _store_samples(connection: Connection, *, count: int, embedded: int) -> None:
    """Store ``count`` samples, the first ``embedded`` with a vector in one of two groups."""
    sample_repository = PostgresSampleRepository(connection)
    generator = np.random.default_rng(0)
    features = []
    for index in range(count):
        sample_repository.upsert(
            Sample(hash=_sample_hash(index), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=32)
        )
        if index < embedded:
            offset = GROUP_OFFSET if index >= SAMPLES_PER_GROUP else 0.0
            vector = tuple(float(value) for value in generator.normal(size=DIMENSIONS) + offset)
            features.append(
                SampleSpectralFeature(sample_hash=_sample_hash(index), vector=vector, computed_at=datetime.now(UTC))
            )
    PostgresSampleSpectralFeatureRepository(connection).replace_all(features)


def _store_module(connection: Connection, module_index: int, sample_indices: tuple[int, ...]) -> str:
    module_repository = PostgresModuleRepository(connection)
    module_hash = _module_hash(module_index)
    module_repository.insert(
        Module(
            hash=module_hash,
            id=module_repository.next_id(),
            filename=f"song{module_index}.mod",
            tracker=TrackerFormat.MOD,
            title="untitled",
            channel_count=4,
            pattern_count=1,
            instrument_count=len(sample_indices),
            sample_count=len(sample_indices),
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    properties_repository = PostgresSamplePropertiesRepository(connection)
    for slot, sample_index in enumerate(sample_indices):
        properties_repository.upsert(
            MODSampleProperties(
                sample_hash=_sample_hash(sample_index),
                occurrence=SampleOccurrence(module_hash=module_hash, instrument_index=slot, sample_slot=0),
                name="sample",
                rate=8363,
                volume=64,
            )
        )
    return module_hash


def _store_two_groups_of_modules(connection: Connection) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Store modules drawing their samples from one of two distant groups of sounds."""
    _store_samples(connection, count=2 * SAMPLES_PER_GROUP, embedded=2 * SAMPLES_PER_GROUP)
    groups: list[tuple[str, ...]] = []
    for group in range(2):
        hashes = []
        for member in range(MODULES_PER_GROUP):
            first = group * SAMPLES_PER_GROUP + member
            sample_indices = tuple(
                group * SAMPLES_PER_GROUP + (first + step) % SAMPLES_PER_GROUP for step in range(SAMPLES_PER_MODULE)
            )
            hashes.append(_store_module(connection, group * MODULES_PER_GROUP + member, sample_indices))
        groups.append(tuple(hashes))
    return groups[0], groups[1]


def _coordinates(connection: Connection) -> dict[str, tuple[float, float]]:
    return {
        coordinate.module_hash: (coordinate.x, coordinate.y)
        for coordinate in PostgresModuleCloudCoordinateRepository(connection).list_all()
    }


def test_modules_with_similar_samples_land_together(connection: Connection, library_root: Path) -> None:
    first_group, second_group = _store_two_groups_of_modules(connection)

    summary = lay_out_and_persist_modules(connection, library_root=library_root)

    coordinates = _coordinates(connection)
    assert summary.modules_placed == 2 * MODULES_PER_GROUP
    assert set(coordinates) == set(first_group) | set(second_group)
    first = np.array([coordinates[module_hash] for module_hash in first_group])
    second = np.array([coordinates[module_hash] for module_hash in second_group])
    assert max(pdist(first).max(), pdist(second).max()) < cdist(first, second).min()


def test_a_run_reports_how_faithfully_it_laid_the_modules_out(connection: Connection, library_root: Path) -> None:
    _store_two_groups_of_modules(connection)

    summary = lay_out_and_persist_modules(connection, library_root=library_root)

    assert summary.preservation is not None
    assert 0.0 < summary.preservation.distance_correlation <= 1.0


def test_a_module_without_embedded_samples_loses_its_coordinate(connection: Connection, library_root: Path) -> None:
    _store_two_groups_of_modules(connection)
    silent_module = _store_module(connection, 99, ())
    PostgresModuleCloudCoordinateRepository(connection).upsert(
        ModuleCloudCoordinate(module_hash=silent_module, x=1.0, y=2.0, computed_at=datetime.now(UTC))
    )

    lay_out_and_persist_modules(connection, library_root=library_root)

    assert silent_module not in _coordinates(connection)


def test_too_few_modules_leave_the_module_cloud_as_it_is(connection: Connection, library_root: Path) -> None:
    _store_samples(connection, count=3, embedded=2)
    module_hashes = [_store_module(connection, index, (index,)) for index in range(3)]
    kept = ModuleCloudCoordinate(module_hash=module_hashes[0], x=1.0, y=2.0, computed_at=datetime.now(UTC))
    PostgresModuleCloudCoordinateRepository(connection).upsert(kept)

    summary = lay_out_and_persist_modules(connection, library_root=library_root)

    assert summary.modules_placed == 0
    assert summary.preservation is None
    assert _coordinates(connection) == {kept.module_hash: (kept.x, kept.y)}


class MeasurementStopped(RuntimeError):
    pass


def test_an_unchanged_library_leaves_its_module_cloud_standing(connection: Connection, library_root: Path) -> None:
    _store_two_groups_of_modules(connection)
    lay_out_and_persist_modules(connection, library_root=library_root)
    laid_out = _coordinates(connection)

    assert lay_out_and_persist_modules(connection, library_root=library_root) is None
    assert _coordinates(connection) == laid_out


def test_a_measurement_stopped_partway_takes_up_after_its_last_batch_and_lands_as_a_straight_run_would(
    connection: Connection, library_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store_two_groups_of_modules(connection)
    monkeypatch.setattr(distance_module, "BATCH_MEMBER_COUNT", SAMPLES_PER_MODULE)
    lay_out_and_persist_modules(connection, library_root=tmp_path / "straight")
    straight = _coordinates(connection)
    measure = run_module.directed_batches

    def stop_after_the_first_batch(*arguments: Any, **keywords: Any) -> Iterator[tuple[range, Any]]:
        batches = measure(*arguments, **keywords)
        yield next(batches)
        raise MeasurementStopped("stopped between batches")

    monkeypatch.setattr(run_module, "directed_batches", stop_after_the_first_batch)
    with pytest.raises(MeasurementStopped):
        lay_out_and_persist_modules(connection, library_root=library_root)
    first_modules: list[int] = []

    def recording(*arguments: Any, first_module: int) -> Iterator[tuple[range, Any]]:
        first_modules.append(first_module)
        return measure(*arguments, first_module=first_module)

    monkeypatch.setattr(run_module, "directed_batches", recording)

    lay_out_and_persist_modules(connection, library_root=library_root)

    assert first_modules[0] > 0
    assert _coordinates(connection) == straight
