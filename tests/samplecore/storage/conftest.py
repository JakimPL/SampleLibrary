from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import Connection, select

from samplecore.hashing import compute_module_hash
from samplecore.models.cloud import CloudPromotion, ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.models.sample_category import CategoryPromotion, SampleCategory
from samplecore.models.sample_file import FileFingerprint
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage.cluster.embedded import state as cluster_state
from samplecore.storage.cluster.embedded.server import EmbeddedCluster
from samplecore.storage.database import metadata
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresCloudPromotionRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository
from samplecore.storage.repositories.sample_category import (
    PostgresCategoryPromotionRepository,
    PostgresSampleCategoryRepository,
)
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

WORKER_ENVIRONMENT_VARIABLE: Final[str] = "PYTEST_XDIST_WORKER"
WORKER_PREFIX: Final[str] = "gw"
FIRST_WORKER: Final[str] = "gw0"
WORKER_PORT_BASE: Final[int] = 25432

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
    build_sandbox(tmp_path, database_url=SANDBOX_DATABASE_URL, service_urls={})
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
    PostgresSampleCategoryRepository(connection).insert_many(
        [
            SampleCategory(
                experiment_id=experiment_id,
                sample_hash=first_sample_hash,
                rank=0,
                label="SNARE",
                score=0.5,
                computed_at=now,
            )
        ]
    )
    PostgresCategoryPromotionRepository(connection).record(
        CategoryPromotion(experiment_id=experiment_id, promoted_at=now)
    )
    PostgresPassCompletionRepository(connection).record(
        PassCompletion(kind=PassKind.MODULES, digest="0" * 64, completed_at=now)
    )
    connection.commit()

    return library_root


@pytest.fixture(scope="module")
def module_cluster_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A library root whose own Postgres server runs for one test module, its owner a superuser.

    The service roles a served catalog API connects as are created by a superuser, which the
    library's own server has and a shared test server need not, so the tests of those roles run
    here. The server prefers a port of the test worker's own, as `test_embedded` explains.
    """
    root = tmp_path_factory.mktemp("library")
    worker = int(os.environ.get(WORKER_ENVIRONMENT_VARIABLE, FIRST_WORKER).removeprefix(WORKER_PREFIX))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cluster_state, "PREFERRED_MANAGED_PORT", WORKER_PORT_BASE + worker)
        cluster = EmbeddedCluster(root)
        cluster.ensure_running()
    try:
        yield root
    finally:
        cluster.stop()
