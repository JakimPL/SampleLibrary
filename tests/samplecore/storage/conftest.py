from __future__ import annotations

import importlib.util
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, select
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_module_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.cloud import CloudPromotion, ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.label_suggestion import SampleLabelSuggestion
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import metadata
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresCloudPromotionRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.equivalence.detect import detect_equivalences
from sampleextract.ingest import ingest_module
from sampleextract.notes.playback_rates import record_playback_rates
from sampleextract.parsing import parse_module


@pytest.fixture
def stored_sample(connection: Connection, sample_hash_a: str) -> Sample:
    sample = Sample(hash=sample_hash_a, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    PostgresSampleRepository(connection).upsert(sample)
    connection.commit()
    return sample


@pytest.fixture
def stored_sample_b(connection: Connection, sample_hash_b: str) -> Sample:
    sample = Sample(hash=sample_hash_b, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    PostgresSampleRepository(connection).upsert(sample)
    connection.commit()
    return sample


@pytest.fixture
def stored_module(connection: Connection, module_hash_a: str) -> Module:
    repository = PostgresModuleRepository(connection)
    module = Module(
        hash=module_hash_a,
        id=repository.next_id(),
        filename="song.it",
        tracker=TrackerFormat.IT,
        title="untitled",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module


@pytest.fixture
def stored_module_b(connection: Connection, module_hash_b: str) -> Module:
    repository = PostgresModuleRepository(connection)
    module = Module(
        hash=module_hash_b,
        id=repository.next_id(),
        filename="song2.it",
        tracker=TrackerFormat.IT,
        title="untitled 2",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module


SANDBOX_DATABASE_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary_dev"

_BUILD_DEV_LIBRARY_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_dev_library.py"


def _load_script(path: Path, name: str) -> types.ModuleType:
    """Imports a script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_dev_library = _load_script(_BUILD_DEV_LIBRARY_PATH, "build_dev_library")


def _ingest_all(connection: Connection, library_root: Path, modules_directory: Path) -> None:
    for path in sorted(modules_directory.iterdir()):
        data = path.read_bytes()
        song = parse_module(data, tracker=FORMAT_LOADERS[path.suffix.lower()])
        ingest_module(
            connection,
            library_root,
            module_hash=compute_module_hash(data),
            tracker=FORMAT_LOADERS[path.suffix.lower()],
            filename=path.name,
            file_size=len(data),
            song=song,
            ingested_at=datetime.now(UTC),
            minimum_sample_frames=512,
        )


@pytest.fixture
def populated_library(connection: Connection, tmp_path: Path) -> Path:
    """Seeds a throwaway catalog with at least one row in every table and at least one stored
    object -- every table the schema declares, not only the ones a plain extraction pass happens to
    touch. Returns the filesystem library root the content store was written under.
    """
    build_dev_library.build_dev_library(tmp_path, database_url=SANDBOX_DATABASE_URL)
    library_root = tmp_path / "catalog"
    _ingest_all(connection, library_root, tmp_path / "modules")
    connection.commit()
    detect_equivalences(connection, library_root)
    connection.commit()
    record_playback_rates(connection)

    first_module = PostgresModuleRepository(connection).list_all()[0]
    sample_hashes = [row.hash for row in connection.execute(select(metadata.tables["sample"].c.hash)).fetchall()]
    first_sample_hash = sample_hashes[0]

    now = datetime.now(UTC)
    PostgresSampleThumbnailRepository(connection).upsert(
        SampleThumbnail(sample_hash=first_sample_hash, bucket_count=2, minimums=(-1.0, -0.5), maximums=(0.5, 1.0))
    )
    PostgresCloudCoordinateRepository(connection).upsert(
        SampleCloudCoordinate(sample_hash=first_sample_hash, x=0.1, y=0.2, computed_at=now)
    )
    PostgresModuleCloudCoordinateRepository(connection).upsert(
        ModuleCloudCoordinate(module_hash=first_module.hash, x=0.3, y=0.4, computed_at=now)
    )
    PostgresSampleSpectralFeatureRepository(connection).upsert(
        SampleSpectralFeature(sample_hash=first_sample_hash, vector=(0.1, 0.2, 0.3), computed_at=now)
    )

    experiment_repository = PostgresExperimentRepository(connection)
    experiment_id = experiment_repository.next_id()
    experiment_repository.insert(
        Experiment(id=experiment_id, backend_name="librosa", params={}, created_at=now, label=None)
    )
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=experiment_id, sample_hash=first_sample_hash, vector=(0.1, 0.2, 0.3), computed_at=now
            )
        ]
    )
    PostgresCloudPromotionRepository(connection).record(CloudPromotion(experiment_id=experiment_id, promoted_at=now))
    PostgresSampleLabelSuggestionRepository(connection).insert_many(
        [
            SampleLabelSuggestion(
                experiment_id=experiment_id,
                sample_hash=first_sample_hash,
                rank=0,
                label="SNARE",
                score=0.5,
                computed_at=now,
            )
        ]
    )
    connection.commit()

    return library_root
