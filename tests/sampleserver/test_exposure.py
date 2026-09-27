from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.annotation import AnnotationSource, SampleAnnotation, SampleFileAnchor
from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.relation import RelationReview, RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.paths import PACKAGES_DIRECTORY
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from sampleserver.messages import CURATION_WITHHELD
from tests.sampleserver.conftest import INFERENCE_URL, SAMPLE_DIRECTORY_NAMES

PACK_DIRECTORY_NAME: Final[str] = SAMPLE_DIRECTORY_NAMES[0]
MODULE_HASH: Final[str] = "c" * 64
MODULE_SAMPLE_HASH: Final[str] = "a" * 64
UNCATALOGED_HASH: Final[str] = "e" * 64
SECRET_LABEL: Final[str] = "CONFIDENTIAL LABEL"
REVIEWER: Final[str] = "a curator's own name"
# The modules allowed to name an exposure: the configuration that reads it and the one policy applying it.
EXPOSURE_READERS: Final[frozenset[Path]] = frozenset(
    {PACKAGES_DIRECTORY / "samplecore" / "config.py", PACKAGES_DIRECTORY / "sampleserver" / "policy.py"}
)


@dataclass(frozen=True)
class SeededLibrary:
    file_sample: SampleFile


@pytest.fixture
def seeded(connection: Connection, tmp_path: Path) -> SeededLibrary:
    """A module sample and a sample found in a pack beside the library, labeled, rated, a favorite, and related by review."""
    path = tmp_path / PACK_DIRECTORY_NAME / "Kicks" / "Deep 01.wav"
    path.parent.mkdir(parents=True)
    soundfile.write(path, np.linspace(-0.5, 0.5, 64), 48000, subtype="PCM_16")
    decoded = decode_sample_file(path)
    file_sample = SampleFile(
        sample_hash=decoded.sample_pcm.sample.hash,
        location=SampleFileLocation(directory=path.parent.parent, relative_path="Kicks/Deep 01.wav"),
        rate=decoded.rate,
        fingerprint=FileFingerprint.of(path.stat()),
    )
    PostgresSampleRepository(connection).upsert(decoded.sample_pcm.sample)
    PostgresSampleFileRepository(connection).upsert(file_sample)
    _seed_module_sample(connection)
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            SampleAnnotation(
                sample_hash=file_sample.sample_hash,
                label=SECRET_LABEL,
                rating=5,
                favorite=True,
                anchor=SampleFileAnchor(location=file_sample.location),
                source=AnnotationSource.SAMPLE,
                annotated_at=datetime.now(UTC),
            ),
        )
    )
    relations = PostgresSampleRelationRepository(connection)
    subject, reference = sorted((MODULE_SAMPLE_HASH, file_sample.sample_hash))
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
    return SeededLibrary(file_sample=file_sample)


def _seed_module_sample(connection: Connection) -> None:
    PostgresSampleRepository(connection).upsert(
        Sample(hash=MODULE_SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
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
            sample_count=1,
            file_size=1024,
            ingested_at=datetime.now(UTC),
        )
    )
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=MODULE_SAMPLE_HASH,
            occurrence=SampleOccurrence(module_hash=MODULE_HASH, instrument_index=0, sample_slot=0),
            name="lead",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def _every_answer(client: TestClient, seeded: SeededLibrary) -> dict[str, str]:
    """Each read the app serves over the seeded library, and some it refuses, as the text a visitor receives."""
    file_hash = seeded.file_sample.sample_hash
    paths = (
        "/samples",
        "/samples?group_by_equivalence=true",
        f"/samples/{file_hash}",
        f"/samples/{file_hash}/preview",
        f"/samples/{file_hash}/relations",
        f"/samples/{file_hash}/similar",
        f"/samples/{MODULE_SAMPLE_HASH}/distance/{file_hash}",
        f"/samples/{UNCATALOGED_HASH}",
        "/cloud",
        "/cloud/labels",
        "/cloud/categories",
        "/cloud/category-tags",
        "/cloud/modules",
        "/modules",
        f"/modules/{MODULE_HASH}",
        "/stats",
        "/curation/access",
        "/curation/annotations/vocabulary",
        "/curation/annotations/tags",
        "/morph/status",
        f"/morph/audio?first={MODULE_SAMPLE_HASH}&second={file_hash}&weight=0.5",
        "/no-such-route",
    )
    return {path: client.get(path).text for path in paths}


def test_a_public_answer_names_no_path_address_or_decision_of_the_person_who_curated_it(
    public_client: TestClient, seeded: SeededLibrary, tmp_path: Path
) -> None:
    private = (tmp_path.as_posix(), INFERENCE_URL, SECRET_LABEL, REVIEWER, "inference.test")

    answers = _every_answer(public_client, seeded)

    leaks = {path: fragment for path, text in answers.items() for fragment in private if fragment in text}
    assert leaks == {}


def test_a_local_answer_shows_the_folder_and_the_decisions_a_person_made(
    client: TestClient, seeded: SeededLibrary, tmp_path: Path
) -> None:
    answers = _every_answer(client, seeded)

    detail = answers[f"/samples/{seeded.file_sample.sample_hash}"]
    assert seeded.file_sample.location.directory.as_posix() in detail
    assert SECRET_LABEL in detail
    assert REVIEWER in answers[f"/samples/{seeded.file_sample.sample_hash}/relations"]


def test_a_public_sample_file_is_named_by_its_folder_with_no_state(
    public_client: TestClient, seeded: SeededLibrary
) -> None:
    detail = public_client.get(f"/samples/{seeded.file_sample.sample_hash}").json()

    assert detail["files"] == [
        {"directory": PACK_DIRECTORY_NAME, "relative_path": "Kicks/Deep 01.wav", "rate": 48000, "available": None}
    ]
    assert (detail["hand_label"], detail["rating"], detail["favorite"]) == (None, None, False)


@pytest.mark.parametrize(
    "query", ["favorites_only=true", "minimum_rating=3", "sort=rating"], ids=("favorites", "rating", "rating order")
)
def test_a_public_listing_narrows_and_orders_by_no_decision(
    public_client: TestClient, seeded: SeededLibrary, query: str
) -> None:
    """An order by rating would tell what the ratings are through the order of the rows."""
    response = public_client.get(f"/samples?{query}")

    assert response.status_code == 422
    assert response.json()["detail"] == CURATION_WITHHELD


@pytest.mark.parametrize("path", ["/cloud/labels", "/curation/annotations/vocabulary", "/curation/annotations/tags"])
def test_a_public_library_serves_no_route_reading_decisions(public_client: TestClient, path: str) -> None:
    assert public_client.get(path).status_code == 404


def test_a_public_library_describes_its_api_nowhere(public_client: TestClient) -> None:
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert public_client.get(path).status_code == 404


def test_a_stored_object_the_catalog_no_longer_holds_is_heard_only_locally(
    client: TestClient, public_client: TestClient, seeded: SeededLibrary, tmp_path: Path
) -> None:
    """A store can keep an object after its sample left the catalog; a site plays what it lists alone."""
    stored = audio_store.object_path(tmp_path, UNCATALOGED_HASH)
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"RIFF")

    assert client.get(f"/samples/{UNCATALOGED_HASH}/audio").status_code == 200
    assert public_client.get(f"/samples/{UNCATALOGED_HASH}/audio").status_code == 404


def test_a_file_outside_the_servers_sample_directories_is_never_opened(
    client: TestClient, connection: Connection, tmp_path: Path
) -> None:
    """The catalog names a folder; the server opens files only in the folders its own configuration lists."""
    elsewhere = tmp_path / "elsewhere" / "Snare.wav"
    elsewhere.parent.mkdir()
    soundfile.write(elsewhere, np.linspace(-0.5, 0.5, 64), 44100, subtype="PCM_16")
    decoded = decode_sample_file(elsewhere)
    PostgresSampleRepository(connection).upsert(decoded.sample_pcm.sample)
    PostgresSampleFileRepository(connection).upsert(
        SampleFile(
            sample_hash=decoded.sample_pcm.sample.hash,
            location=SampleFileLocation(directory=elsewhere.parent, relative_path=elsewhere.name),
            rate=decoded.rate,
            fingerprint=FileFingerprint.of(elsewhere.stat()),
        )
    )

    response = client.get(f"/samples/{decoded.sample_pcm.sample.hash}/audio")
    detail = client.get(f"/samples/{decoded.sample_pcm.sample.hash}").json()

    assert response.status_code == 404
    assert detail["files"][0]["available"] is None


@pytest.mark.parametrize(
    ("client_address", "base_url"),
    [(("127.0.0.1", 50000), "http://rebound.example"), (("192.168.1.20", 50000), "http://localhost")],
    ids=("a page that points its own name at this computer", "a device on the network"),
)
def test_a_library_on_this_computer_alone_answers_no_one_else(
    client: TestClient, client_address: tuple[str, int], base_url: str
) -> None:
    with TestClient(client.app, base_url=f"{base_url}/api", client=client_address) as elsewhere:
        response = elsewhere.get("/stats")

    assert response.status_code == 403


def test_no_module_but_the_configuration_and_the_policy_names_an_exposure() -> None:
    """Every behavior an exposure changes reads it through `ServingPolicy`, so no source file keeps a rule of its own."""
    naming = sorted(
        str(path.relative_to(PACKAGES_DIRECTORY))
        for path in PACKAGES_DIRECTORY.rglob("*.py")
        if path not in EXPOSURE_READERS and _names_exposure(path)
    )

    assert naming == []


def _names_exposure(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(node, ast.Name) and node.id == "Exposure" for node in ast.walk(tree))
