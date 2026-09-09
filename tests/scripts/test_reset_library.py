from __future__ import annotations

import importlib.util
import types
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection, func, select

from samplecore.hashing import compute_module_hash
from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.cloud import ModuleCloudCoordinate, SampleCloudCoordinate
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.module import Module
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.spectral import SampleSpectralFeature
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import metadata
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from sampleextract.discovery import FORMAT_LOADERS
from sampleextract.equivalence.detect import detect_equivalences
from sampleextract.ingest import ingest_module
from sampleextract.notes.playback_rates import record_playback_rates
from sampleextract.parsing import parse_module

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reset_library.py"
_BUILD_DEV_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_dev_library.py"


def _load_script(path: Path, name: str) -> types.ModuleType:
    """Imports a script by file path -- it lives outside every installed package, by design."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reset_library = _load_script(_SCRIPT_PATH, "reset_library")
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


def _populate_library(connection: Connection, tmp_path: Path) -> Path:
    """Seeds a throwaway catalog with at least one row in every table and at least one stored
    object -- every table the schema declares, not only the ones a plain extraction pass happens to
    touch. Returns the filesystem library root the content store was written under.
    """
    build_dev_library.build_dev_library(tmp_path)
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
    connection.commit()

    return library_root


def _row_counts(connection: Connection) -> dict[str, int]:
    return {
        table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
        for table in metadata.sorted_tables
    }


def test_reset_library_empties_every_table_and_the_content_store(connection: Connection, tmp_path: Path) -> None:
    library_root = _populate_library(connection, tmp_path)
    before = _row_counts(connection)
    assert all(count > 0 for count in before.values()), f"fixture left an empty table: {before}"
    objects_directory = library_root / "objects"
    assert any(objects_directory.rglob("*.wav"))

    reset_library.reset_library(connection, library_root)
    connection.commit()

    after = _row_counts(connection)
    assert all(count == 0 for count in after.values()), f"reset left rows behind: {after}"
    assert objects_directory.is_dir()
    assert list(objects_directory.iterdir()) == []


def test_reset_library_leaves_hand_labels_untouched(connection: Connection, tmp_path: Path) -> None:
    """Hand labels are the one thing in this library nobody can regenerate, so a purge leaves them.

    They live on a metadata of their own, which is what puts them beyond the reach of the loop over
    ``metadata.sorted_tables`` that empties everything else.
    """
    library_root = _populate_library(connection, tmp_path)
    module = PostgresModuleRepository(connection).list_all()[0]
    occurrence_row = connection.execute(
        select(metadata.tables["sample_properties"]).where(
            metadata.tables["sample_properties"].c.module_id == module.id
        )
    ).fetchone()
    assert occurrence_row is not None

    annotation_repository = PostgresSampleAnnotationRepository(connection)
    annotation_repository.replace_many(
        (
            SampleAnnotation(
                sample_hash=occurrence_row.sample_hash,
                label="warm pad",
                rating=None,
                favorite=False,
                occurrence=SampleOccurrence(
                    module_hash=module.hash,
                    instrument_index=occurrence_row.instrument_index,
                    sample_slot=occurrence_row.sample_slot,
                ),
                module_filename=module.filename,
                sample_name=occurrence_row.name,
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    connection.commit()

    reset_library.reset_library(connection, library_root)
    connection.commit()

    assert all(count == 0 for count in _row_counts(connection).values())
    surviving = annotation_repository.get(occurrence_row.sample_hash)
    assert surviving is not None
    assert surviving.label == "warm pad"
    assert surviving.occurrence.module_hash == module.hash


def test_reset_library_leaves_the_schema_usable_afterward(connection: Connection, tmp_path: Path) -> None:
    library_root = _populate_library(connection, tmp_path)

    reset_library.reset_library(connection, library_root)
    connection.commit()

    module_repository = PostgresModuleRepository(connection)
    module_repository.insert(
        Module(
            hash=format(1, "064x"),
            id=module_repository.next_id(),
            filename="fresh.it",
            tracker=TrackerFormat.IT,
            title="fresh",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    connection.commit()

    assert connection.execute(select(func.count()).select_from(metadata.tables["module"])).scalar_one() == 1


def test_confirm_flag_defaults_to_false() -> None:
    arguments = reset_library._parse_arguments([])

    assert arguments.confirm is False


def test_confirm_flag_can_be_set() -> None:
    arguments = reset_library._parse_arguments(["--confirm"])

    assert arguments.confirm is True


def test_main_without_confirm_changes_nothing(connection: Connection, tmp_path: Path) -> None:
    _populate_library(connection, tmp_path)
    before = _row_counts(connection)

    reset_library.main([])

    assert _row_counts(connection) == before
