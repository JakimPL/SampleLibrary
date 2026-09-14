from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection, delete
from trackmod.trackers.xm.tuning import Tuning

from samplecore.anchoring import anchors_by_hash, relinked_hash
from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation, SampleFileAnchor
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.storage.database import sample_file
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

DIRECTORY = Path("/samples")


def _add_file(connection: Connection, sample: Sample, relative_path: str) -> SampleFileLocation:
    location = SampleFileLocation(directory=DIRECTORY, relative_path=relative_path)
    PostgresSampleFileRepository(connection).upsert(
        SampleFile(
            sample_hash=sample.hash,
            location=location,
            rate=44100,
            fingerprint=FileFingerprint(size_bytes=64, modified_ns=0),
        )
    )
    connection.commit()
    return location


def _annotated(sample: Sample, anchor: SampleFileAnchor) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample.hash,
        label="kick",
        rating=None,
        favorite=False,
        anchor=anchor,
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )


def test_a_sample_found_in_a_module_is_anchored_to_its_slot_ahead_of_its_files(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    occurrence = SampleOccurrence(module_hash=stored_module.hash, instrument_index=0, sample_slot=0)
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=stored_sample.hash,
            occurrence=occurrence,
            name="smp01",
            rate=8363,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )
    _add_file(connection, stored_sample, "Kicks/Deep 01.wav")

    anchors = anchors_by_hash(connection, (stored_sample.hash,))

    assert anchors == {
        stored_sample.hash: ModuleSlotAnchor(
            occurrence=occurrence, module_filename=stored_module.filename, sample_name="smp01"
        )
    }


def test_a_sample_found_only_in_files_is_anchored_to_the_first_of_them(
    connection: Connection, stored_sample: Sample
) -> None:
    _add_file(connection, stored_sample, "Kicks/Deep 02.wav")
    first = _add_file(connection, stored_sample, "Kicks/Deep 01.wav")

    assert anchors_by_hash(connection, (stored_sample.hash,)) == {stored_sample.hash: SampleFileAnchor(location=first)}


def test_a_file_anchor_relinks_to_the_sample_its_file_holds_now(
    connection: Connection, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    location = _add_file(connection, stored_sample, "Kicks/Deep 01.wav")
    annotation = _annotated(stored_sample, SampleFileAnchor(location=location))
    _add_file(connection, stored_sample_b, "Kicks/Deep 01.wav")

    assert relinked_hash(connection, annotation) == stored_sample_b.hash

    connection.execute(delete(sample_file))
    connection.commit()

    assert relinked_hash(connection, annotation) is None
