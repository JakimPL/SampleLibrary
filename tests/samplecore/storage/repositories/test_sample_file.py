from __future__ import annotations

from pathlib import Path

from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository

DIRECTORY = Path("/samples/packs")


def _sample_file(sample_hash: str, relative_path: str, *, rate: int = 44100, size_bytes: int = 1024) -> SampleFile:
    return SampleFile(
        sample_hash=sample_hash,
        location=SampleFileLocation(directory=DIRECTORY, relative_path=relative_path),
        rate=rate,
        fingerprint=FileFingerprint(size_bytes=size_bytes, modified_ns=1_700_000_000_000_000_000),
    )


def test_a_sample_file_round_trips_through_get(connection: Connection, stored_sample: Sample) -> None:
    repository = PostgresSampleFileRepository(connection)
    kick = _sample_file(stored_sample.hash, "drums/kick.wav")

    repository.upsert(kick)

    assert repository.get(kick.location) == kick
    assert repository.get(SampleFileLocation(directory=DIRECTORY, relative_path="drums/snare.wav")) is None


def test_upserting_a_location_again_follows_the_file_to_what_it_holds_now(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleFileRepository(connection)
    repository.upsert(_sample_file(stored_sample.hash, "drums/kick.wav"))
    rewritten = _sample_file(stored_sample_b.hash, "drums/kick.wav", rate=48000, size_bytes=2048)

    repository.upsert(rewritten)

    assert repository.list_all() == (rewritten,)


def test_listings_come_in_location_order(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    repository = PostgresSampleFileRepository(connection)
    snare = _sample_file(stored_sample_b.hash, "drums/snare.wav")
    kick_copy = _sample_file(stored_sample.hash, "Kick copy.wav")
    kick = _sample_file(stored_sample.hash, "drums/kick.wav")
    for sample_file in (snare, kick, kick_copy):
        repository.upsert(sample_file)

    assert repository.list_all() == (kick_copy, kick, snare)
    assert repository.list_for_samples([stored_sample.hash]) == (kick_copy, kick)
    assert repository.count() == 3
