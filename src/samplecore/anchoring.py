from __future__ import annotations

from sqlalchemy import Connection

from samplecore.models.annotation import AnnotationAnchor, ModuleSlotAnchor, SampleAnnotation, SampleFileAnchor
from samplecore.models.sample_file import SampleFile
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository


def anchors_by_hash(connection: Connection, sample_hashes: tuple[str, ...]) -> dict[str, AnnotationAnchor]:
    """The anchor each of ``sample_hashes`` gets from the catalog, for the samples it holds a module slot or a file of.

    A sample's hash depends on how this project hashes audio, so an annotation keyed on the hash
    alone would be lost the moment that changes. A sample found in a module is anchored to the
    occurrence lowest in ``(module_hash, instrument_index, sample_slot)`` order, recorded together
    with the module's filename and the occurrence's name, which stay readable to a person even when
    neither hash resolves. A sample found in files alone is anchored to its file lowest in location
    order. Both choices are deterministic, so revisiting the same sample keeps naming the same place.
    """
    anchors: dict[str, AnnotationAnchor] = {}
    anchors.update(_file_anchors(connection, sample_hashes))
    anchors.update(_module_slot_anchors(connection, sample_hashes))
    return anchors


def relinked_hash(connection: Connection, annotation: SampleAnnotation) -> str | None:
    """The hash an annotation's anchor holds now, for an annotation whose sample was rehashed.

    A module slot is read back through its module, found by its own hash, and a sample file through
    the catalog's row for its location. ``None`` where the module, the slot or the file is no longer
    cataloged, which is what a report of annotations needing a person's attention is built from.
    """
    match annotation.anchor:
        case ModuleSlotAnchor() as anchor:
            for properties in PostgresSamplePropertiesRepository(connection).list_for_module(
                anchor.occurrence.module_hash
            ):
                if properties.occurrence == anchor.occurrence:
                    return properties.sample_hash
            return None
        case SampleFileAnchor() as anchor:
            sample_file = PostgresSampleFileRepository(connection).get(anchor.location)
            return sample_file.sample_hash if sample_file is not None else None


def _module_slot_anchors(connection: Connection, sample_hashes: tuple[str, ...]) -> dict[str, ModuleSlotAnchor]:
    occurrences_by_hash: dict[str, list[TrackerSampleProperties]] = {}
    for properties in PostgresSamplePropertiesRepository(connection).list_for_samples(sample_hashes):
        occurrences_by_hash.setdefault(properties.sample_hash, []).append(properties)

    lowest_by_hash = {sample_hash: _lowest_occurrence(found) for sample_hash, found in occurrences_by_hash.items()}
    module_hashes = sorted({lowest.occurrence.module_hash for lowest in lowest_by_hash.values()})
    modules_by_hash = PostgresModuleRepository(connection).get_many(module_hashes)
    return {
        sample_hash: ModuleSlotAnchor(
            occurrence=lowest.occurrence,
            module_filename=modules_by_hash[lowest.occurrence.module_hash].filename,
            sample_name=lowest.name,
        )
        for sample_hash, lowest in lowest_by_hash.items()
    }


def _file_anchors(connection: Connection, sample_hashes: tuple[str, ...]) -> dict[str, SampleFileAnchor]:
    first_by_hash: dict[str, SampleFile] = {}
    for sample_file in PostgresSampleFileRepository(connection).list_for_samples(sample_hashes):
        first_by_hash.setdefault(sample_file.sample_hash, sample_file)
    return {
        sample_hash: SampleFileAnchor(location=sample_file.location)
        for sample_hash, sample_file in first_by_hash.items()
    }


def _lowest_occurrence(properties: list[TrackerSampleProperties]) -> TrackerSampleProperties:
    return min(
        properties,
        key=lambda item: (item.occurrence.module_hash, item.occurrence.instrument_index, item.occurrence.sample_slot),
    )
