from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient
from psycopg import errors as postgres_errors
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.pool import NullPool
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecloud.categories.vocabulary import INSTRUMENT_VOCABULARY
from samplecore.config import (
    CONFIG_PATH_ENVIRONMENT_VARIABLE,
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE,
)
from samplecore.exit_status import ExitStatus
from samplecore.models.annotation import AnnotationSource, SampleAnnotation, SampleFileAnchor
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import SampleFeatureVector
from samplecore.models.module import Module
from samplecore.models.module_link import ModuleLink
from samplecore.models.relation import RelationReview, RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_category import CategoryPromotion, SampleCategory
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.service_role import ServiceRole
from samplecore.models.tracker import TrackerFormat
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage import audio_store
from samplecore.storage.cluster.embedded.state import managed_catalog_url
from samplecore.storage.curation import CURATION_SCHEMA, curation_metadata
from samplecore.storage.database import connect
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.module_link import PostgresModuleLinkRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_category import (
    PostgresCategoryPromotionRepository,
    PostgresSampleCategoryRepository,
)
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from sampleripper.paths import publication_directory
from sampleripper.publish import cli as publish_cli
from sampleripper.publish.messages import NOT_A_PUBLICATION, OWN_VOCABULARY, PRIVATE_VALUE
from sampleripper.publish.rules import RULES, Rule, catalog_tables
from sampleripper.publish.target import READER_ROLE, PublishRefusedError, target_url
from sampleserver.app import create_app
from tests.sampleserver.conftest import INFERENCE_URL, PUBLIC_SERVER

PROGRAM: Final[str] = "sampleripper publish"
MODULE_HASH: Final[str] = "c" * 64
MODULE_PAGE_URL: Final[str] = "https://www.modules.pl/?id=module&mod=9752"
MODULE_SAMPLES: Final[tuple[str, ...]] = ("a" * 64, "b" * 64)
READER_PASSWORD: Final[str] = "p" * 32
SECRET_LABEL: Final[str] = "CONFIDENTIAL LABEL"
REVIEWER: Final[str] = "a curator's own name"
OWN_SCORING_LABEL: Final[str] = "my own note on this scoring"
PUBLISHED_PACK: Final[str] = "Free Pack"
UNPUBLISHED_PACK: Final[str] = "Vengeance"
# What a site's reader, a role anyone who took the site over would hold, must not do.
REFUSED_TO_THE_READER: Final[tuple[str, ...]] = (
    "CREATE TEMPORARY TABLE intruder (id integer)",
    "CREATE TABLE public.intruder (id integer)",
    "CREATE SCHEMA intruder",
    "DELETE FROM sample",
    "UPDATE module SET title = 'defaced'",
    "TRUNCATE sample_file",
    "INSERT INTO category_promotion (experiment_id, promoted_at) VALUES (1, now())",
    "COPY (SELECT 1) TO PROGRAM 'true'",
    "COPY sample FROM PROGRAM 'true'",
    "SELECT pg_read_file('/etc/hostname')",
    "SELECT pg_ls_dir('.')",
    "SELECT lo_import('/etc/hostname')",
    f"ALTER ROLE {READER_ROLE} SUPERUSER",
    f"ALTER ROLE {READER_ROLE} CREATEROLE",
    "CREATE ROLE intruder LOGIN PASSWORD 'intruder'",
    "ALTER SYSTEM SET log_statement = 'none'",
)

pytestmark = pytest.mark.usefixtures("worker_cluster_port")


@dataclass(frozen=True)
class SeededLibrary:
    root: Path
    config_path: Path
    published_file: SampleFile
    unpublished_file: SampleFile

    @property
    def catalog_url(self) -> str:
        return managed_catalog_url(self.root)


def _wav(path: Path, frequency: float) -> SampleFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, 0.5 * np.sin(np.linspace(0.0, frequency, 256)), 44100, subtype="PCM_16")
    decoded = decode_sample_file(path)
    return SampleFile(
        sample_hash=decoded.sample_pcm.sample.hash,
        location=SampleFileLocation(directory=path.parent, relative_path=path.name),
        rate=decoded.rate,
        fingerprint=FileFingerprint.of(path.stat()),
    )


@pytest.fixture(scope="module")
def library(module_cluster_root: Path) -> SeededLibrary:
    """A library holding a module's two samples, one sample in a pack to publish, and one in a pack that stays home.

    It carries everything that stays home as well: a label, a reviewed relation, a scoring's own
    note, a fingerprint and an experiment's vectors.
    """
    root = module_cluster_root
    published_file = _wav(root.parent / PUBLISHED_PACK / "Kick 01.wav", 40.0)
    unpublished_file = _wav(root.parent / UNPUBLISHED_PACK / "Snare 01.wav", 90.0)
    with closing(connect(managed_catalog_url(root))) as connection:
        _seed(connection, root, published_file=published_file, unpublished_file=unpublished_file)
    config_path = root.parent / "config.toml"
    config_path.write_text(
        f'[library]\nlibrary_root = "{root.as_posix()}"\n'
        f'sample_directories = ["{published_file.location.directory.as_posix()}", '
        f'"{unpublished_file.location.directory.as_posix()}"]\n'
        f'[publish]\nsample_directories = ["{published_file.location.directory.as_posix()}"]\n',
        encoding="utf-8",
    )
    return SeededLibrary(
        root=root, config_path=config_path, published_file=published_file, unpublished_file=unpublished_file
    )


def _seed(connection: Connection, root: Path, *, published_file: SampleFile, unpublished_file: SampleFile) -> None:
    samples = PostgresSampleRepository(connection)
    for sample_hash in MODULE_SAMPLES:
        samples.upsert(Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8))
        stored = audio_store.object_path(root, sample_hash)
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(f"RIFF-{sample_hash[0]}".encode())
    modules = PostgresModuleRepository(connection)
    modules.insert(
        Module(
            hash=MODULE_HASH,
            id=modules.next_id(),
            filename="song.xm",
            tracker=TrackerFormat.XM,
            title="a song",
            channel_count=4,
            pattern_count=1,
            instrument_count=1,
            sample_count=2,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    PostgresModuleLinkRepository(connection).upsert_many((ModuleLink(module_hash=MODULE_HASH, url=MODULE_PAGE_URL),))
    for slot, sample_hash in enumerate(MODULE_SAMPLES):
        PostgresSamplePropertiesRepository(connection).upsert(
            XMSampleProperties(
                sample_hash=sample_hash,
                occurrence=SampleOccurrence(module_hash=MODULE_HASH, instrument_index=0, sample_slot=slot),
                name="lead",
                rate=8363,
                volume=64,
                tuning=Tuning(relative_note=0, finetune=0),
            )
        )
    for found in (published_file, unpublished_file):
        samples.upsert(Sample(hash=found.sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=256))
        PostgresSampleFileRepository(connection).upsert(found)
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            SampleAnnotation(
                sample_hash=published_file.sample_hash,
                label=SECRET_LABEL,
                rating=5,
                favorite=True,
                anchor=SampleFileAnchor(location=published_file.location),
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    relations = PostgresSampleRelationRepository(connection)
    for other in (published_file.sample_hash, unpublished_file.sample_hash):
        subject, reference = sorted((MODULE_SAMPLES[0], other))
        relations.upsert(
            SampleRelation(
                id=relations.next_id(),
                subject_hash=subject,
                reference_hash=reference,
                relation_type=RelationType.AMPLIFICATION_VARIANT,
                method="test",
                confidence=1.0,
                evidence={},
                detected_at=datetime.now(UTC),
                review=RelationReview(confirmed=True, reviewed_at=datetime.now(UTC), reviewed_by=REVIEWER),
            )
        )
    experiments = PostgresExperimentRepository(connection)
    scoring = experiments.create(
        backend_name="zero_shot",
        label=OWN_SCORING_LABEL,
        params={"vocabulary": list(INSTRUMENT_VOCABULARY), "checkpoint": str(root / "models" / "clap")},
        key="clap-nominal-0000aaaa",
    )
    everyone = (*MODULE_SAMPLES, published_file.sample_hash, unpublished_file.sample_hash)
    PostgresSampleCategoryRepository(connection).insert_many(
        [
            SampleCategory(
                experiment_id=scoring,
                sample_hash=sample_hash,
                rank=0,
                label="KICK",
                score=0.5,
                computed_at=datetime.now(UTC),
            )
            for sample_hash in everyone
        ]
    )
    PostgresCategoryPromotionRepository(connection).record(
        CategoryPromotion(experiment_id=scoring, promoted_at=datetime.now(UTC))
    )
    learned = experiments.create(backend_name="learned", label=None, params={}, key=None)
    PostgresSampleFeatureVectorRepository(connection).insert_many(
        [
            SampleFeatureVector(
                experiment_id=learned, sample_hash=MODULE_SAMPLES[0], vector=(1.0, 2.0), computed_at=datetime.now(UTC)
            )
        ]
    )
    connection.execute(
        text(
            "INSERT INTO sample_fingerprint (sample_hash, version, silent, trimmed_frames) VALUES (:hash, 1, true, 0)"
        ),
        {"hash": MODULE_SAMPLES[1]},
    )
    connection.commit()


@pytest.fixture
def target(library: SeededLibrary) -> Iterator[str]:
    """An empty database of the library's own server, a stand-in for a site's."""
    name = f"site_{uuid.uuid4().hex[:12]}"
    administrator = create_engine(library.catalog_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with administrator.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(library.catalog_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with administrator.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        administrator.dispose()


@pytest.fixture
def publishing(library: SeededLibrary, monkeypatch: pytest.MonkeyPatch) -> SeededLibrary:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(library.config_path))
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv(PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE, READER_PASSWORD)
    return library


def _publish(target: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE, target)
    publish_cli.main([], prog=PROGRAM)


def _rows(url: str, query: str) -> list[tuple[object, ...]]:
    with closing(connect(url, read_only=True)) as connection:
        return [tuple(row) for row in connection.execute(text(query))]


def test_every_table_a_catalog_holds_has_a_rule() -> None:
    """A table added to the catalog is published only once someone decided which of its rows go."""
    assert set(RULES) == {table.fullname for table in catalog_tables()}
    assert all(RULES[table.fullname] is Rule.EMPTY for table in curation_metadata.sorted_tables)


def test_a_publication_carries_the_catalog_and_nothing_that_stays_home(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(target, monkeypatch)

    published = {str(row[0]) for row in _rows(target, "SELECT hash FROM sample")}
    assert published == {*MODULE_SAMPLES, publishing.published_file.sample_hash}
    assert _rows(target, "SELECT directory, relative_path FROM sample_file") == [(f"/{PUBLISHED_PACK}", "Kick 01.wav")]
    assert _rows(target, "SELECT reviewed_confirmed, reviewed_by FROM sample_relation") == [(None, None)]
    assert _rows(target, "SELECT label, key FROM experiment") == [(None, None)]
    assert _rows(target, "SELECT module_hash, url FROM module_link") == [(MODULE_HASH, MODULE_PAGE_URL)]
    assert [json.loads(str(row[0])) for row in _rows(target, "SELECT params FROM experiment")] == [
        {"vocabulary": list(INSTRUMENT_VOCABULARY)}
    ]
    assert len(_rows(target, "SELECT * FROM sample_category")) == len(published)
    for table in ("sample_fingerprint", "sample_feature_vector", "cloud_promotion", "pass_completion"):
        assert _rows(target, f"SELECT count(*) FROM {table}") == [(0,)]
    for table in curation_metadata.sorted_tables:
        assert _rows(target, f"SELECT count(*) FROM {CURATION_SCHEMA}.{table.name}") == [(0,)]
    tree = publication_directory(publishing.root)
    assert {path.stem for path in (tree / "objects").glob("*/*.wav")} == published


def test_the_sites_reader_reads_the_publication_and_creates_nothing(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(target, monkeypatch)
    reader = make_url(target).set(username=READER_ROLE, password=READER_PASSWORD).render_as_string(hide_password=False)

    allowed = []
    with closing(create_engine(reader, poolclass=NullPool, isolation_level="AUTOCOMMIT").connect()) as connection:
        assert connection.execute(text("SELECT count(*) FROM sample")).scalar_one() == 3
        for statement in (*REFUSED_TO_THE_READER, f'SET ROLE "{make_url(target).username}"'):
            try:
                connection.execute(text(statement))
            except ProgrammingError as refusal:
                if not isinstance(refusal.orig, postgres_errors.InsufficientPrivilege):
                    raise
            else:
                allowed.append(statement)

    assert allowed == []


def test_a_site_serves_its_publication_to_anyone(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(target, monkeypatch)
    reader = make_url(target).set(username=READER_ROLE, password=READER_PASSWORD).render_as_string(hide_password=False)
    application = create_app(
        reader,
        publication_directory(publishing.root),
        INFERENCE_URL,
        role=ServiceRole.READER,
        server=PUBLIC_SERVER,
        sample_directories=(),
        frontend_directory=None,
    )

    with TestClient(application, base_url="http://site.example/api") as client:
        listing = client.get("/samples").json()
        heard = client.get(f"/samples/{publishing.published_file.sample_hash}/audio")
        withheld = client.get(f"/samples/{publishing.unpublished_file.sample_hash}")
        stats = client.get("/stats")

    assert listing["total"] == 3
    assert heard.status_code == 200
    assert heard.content == audio_store.encode_wav(
        decode_sample_file(publishing.published_file.location.path).sample_pcm
    )
    assert withheld.status_code == 404
    assert stats.status_code == 200


def test_a_second_publication_replaces_the_first_and_the_readers_password(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(target, monkeypatch)
    monkeypatch.setenv(PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE, "q" * 32)

    _publish(target, monkeypatch)

    assert _rows(target, "SELECT count(*) FROM sample") == [(3,)]
    old = make_url(target).set(username=READER_ROLE, password=READER_PASSWORD).render_as_string(hide_password=False)
    with pytest.raises(OperationalError):
        connect(old, read_only=True).close()


def test_a_database_holding_a_catalog_no_publication_wrote_is_left_alone(
    publishing: SeededLibrary, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pointed at the library itself, a publication would empty it; it refuses before touching anything."""
    with pytest.raises(SystemExit) as raised:
        _publish(publishing.catalog_url, monkeypatch)

    assert raised.value.code == ExitStatus.REFUSED
    assert NOT_A_PUBLICATION in capsys.readouterr().err
    assert _rows(publishing.catalog_url, "SELECT count(*) FROM curation.sample_annotation") == [(1,)]


def test_a_path_of_this_computer_in_any_published_column_rolls_the_publication_back(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with closing(connect(publishing.catalog_url)) as connection:
        connection.execute(text("UPDATE module SET title = :title"), {"title": f"{publishing.root}/secret.xm"})
        connection.commit()
    try:
        with pytest.raises(SystemExit) as raised:
            _publish(target, monkeypatch)
    finally:
        with closing(connect(publishing.catalog_url)) as connection:
            connection.execute(text("UPDATE module SET title = 'a song'"))
            connection.commit()

    assert raised.value.code == ExitStatus.REFUSED
    assert PRIVATE_VALUE.format(table="module", column="title") in capsys.readouterr().err
    assert _rows(target, "SELECT to_regclass('public.sample') IS NULL") == [(True,)]


def test_categories_scored_with_a_vocabulary_of_ones_own_are_refused(
    publishing: SeededLibrary, target: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A vocabulary built from hand labels carries their wording, which stays home."""
    with closing(connect(publishing.catalog_url)) as connection:
        original = connection.execute(
            text("SELECT params FROM experiment WHERE backend_name = 'zero_shot'")
        ).scalar_one()
        connection.execute(
            text("UPDATE experiment SET params = :params WHERE backend_name = 'zero_shot'"),
            {"params": json.dumps({"vocabulary": ["KICK", "MY OWN WORDING"]})},
        )
        connection.commit()
    try:
        with pytest.raises(SystemExit) as raised:
            _publish(target, monkeypatch)
    finally:
        with closing(connect(publishing.catalog_url)) as connection:
            connection.execute(
                text("UPDATE experiment SET params = :params WHERE backend_name = 'zero_shot'"), {"params": original}
            )
            connection.commit()

    assert raised.value.code == ExitStatus.REFUSED
    assert OWN_VOCABULARY in capsys.readouterr().err


@pytest.mark.parametrize(
    ("given", "refused"),
    [
        ("postgresql://postgres:x@proxy.example:5432/railway?sslmode=disable", True),
        ("postgresql://postgres:x@proxy.example:5432/railway?sslmode=prefer", True),
        ("mysql://root:x@proxy.example/railway", True),
        ("postgresql://postgres:x@/railway?host=proxy.example", True),
        ("postgresql://postgres:x@127.0.0.1/railway?hostaddr=203.0.113.9", True),
        ("postgresql://postgres:x@127.0.0.1/railway?service=site", True),
    ],
)
def test_a_target_reached_without_tls_or_through_another_database_is_refused(given: str, refused: bool) -> None:
    with pytest.raises(PublishRefusedError):
        target_url({PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE: given})


def test_a_target_over_the_internet_is_reached_over_tls_the_password_binds() -> None:
    url = target_url({PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE: "postgresql://postgres:x@proxy.example:5432/railway"})

    assert url.drivername == "postgresql+psycopg"
    assert (url.query["sslmode"], url.query["channel_binding"]) == ("require", "require")


def test_a_target_on_this_computer_is_reached_as_named() -> None:
    url = target_url({PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE: "postgresql+psycopg://owner:x@127.0.0.1:5432/site"})

    assert "sslmode" not in url.query
