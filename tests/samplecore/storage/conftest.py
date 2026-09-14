from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, select

from samplecore.hashing import compute_module_hash
from samplecore.models.cloud import CloudPromotion, ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.label_suggestion import SampleLabelSuggestion, SuggestionPromotion
from samplecore.models.sample_file import FileFingerprint
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage.database import metadata
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresCloudPromotionRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.label_suggestion import (
    PostgresSampleLabelSuggestionRepository,
    PostgresSuggestionPromotionRepository,
)
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from samplecore.storage.sample_audio import SampleAudio
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.equivalence.detect import detect_equivalences
from sampleextract.files.discovery import discover_sample_files
from sampleextract.files.ingest import ingest_sample_file
from sampleextract.ingest import ingest_module
from sampleextract.notes.playback_rates import record_playback_rates
from sampleextract.parsing import parse_module
from samplelibrary.sandbox.build import SAMPLE_PACK_DIRECTORY_NAME, build_sandbox

SANDBOX_DATABASE_URL = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary_dev"


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


def _catalog_the_sample_pack(connection: Connection, sample_pack_directory: Path) -> None:
    for location in discover_sample_files((sample_pack_directory,), exclusions=()).locations:
        ingest_sample_file(
            connection,
            location=location,
            decoded=decode_sample_file(location.path),
            fingerprint=FileFingerprint.of(location.path.stat()),
        )


@pytest.fixture
def populated_library(connection: Connection, tmp_path: Path) -> Path:
    """Seeds a throwaway catalog with at least one row in every table and at least one stored
    object -- every table the schema declares, not only the ones a plain extraction pass happens to
    touch. Returns the filesystem library root the content store was written under.
    """
    build_sandbox(tmp_path, database_url=SANDBOX_DATABASE_URL)
    library_root = tmp_path / "catalog"
    _ingest_all(connection, library_root, tmp_path / "modules")
    connection.commit()
    detect_equivalences(connection, SampleAudio.from_catalog(connection, library_root))
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
    _catalog_the_sample_pack(connection, tmp_path / SAMPLE_PACK_DIRECTORY_NAME)
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
    PostgresSuggestionPromotionRepository(connection).record(
        SuggestionPromotion(experiment_id=experiment_id, promoted_at=now)
    )
    connection.commit()

    return library_root
