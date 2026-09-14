from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.models.annotation import SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence, TrackerSampleProperties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository


@dataclass(frozen=True)
class Anchor:
    """The module slot an annotation stays findable through, with the names a person recognizes it by."""

    occurrence: SampleOccurrence
    module_filename: str
    sample_name: str

    @classmethod
    def of(cls, annotation: SampleAnnotation) -> Anchor:
        """The anchor an annotation already carries."""
        return cls(
            occurrence=annotation.occurrence,
            module_filename=annotation.module_filename,
            sample_name=annotation.sample_name,
        )


def anchors_by_hash(connection: Connection, sample_hashes: tuple[str, ...]) -> dict[str, Anchor]:
    """The anchor each of ``sample_hashes`` gets from the catalog, for the samples it holds an occurrence of.

    A sample's hash depends on how this project hashes audio, so an annotation keyed on the hash
    alone would be lost the moment that changes. The anchor is the occurrence lowest in
    ``(module_hash, instrument_index, sample_slot)`` order -- a deterministic choice, so revisiting
    the same sample keeps naming the same slot -- recorded together with the module's filename and
    the occurrence's name, which stay readable to a person even when neither hash resolves.
    """
    occurrences_by_hash: dict[str, list[TrackerSampleProperties]] = {}
    for properties in PostgresSamplePropertiesRepository(connection).list_for_samples(sample_hashes):
        occurrences_by_hash.setdefault(properties.sample_hash, []).append(properties)

    lowest_by_hash = {sample_hash: _lowest_occurrence(found) for sample_hash, found in occurrences_by_hash.items()}
    module_hashes = sorted({lowest.occurrence.module_hash for lowest in lowest_by_hash.values()})
    modules_by_hash = PostgresModuleRepository(connection).get_many(module_hashes)
    return {
        sample_hash: Anchor(
            occurrence=lowest.occurrence,
            module_filename=modules_by_hash[lowest.occurrence.module_hash].filename,
            sample_name=lowest.name,
        )
        for sample_hash, lowest in lowest_by_hash.items()
    }


def relinked_hash(connection: Connection, annotation: SampleAnnotation) -> str | None:
    """The hash the annotated module slot holds now, for an annotation whose sample was rehashed.

    Reads the anchor back through the catalog: the module is found by its own hash, and the slot it
    names gives whatever sample sits there today. ``None`` where the module or the slot is no longer
    cataloged, which is what a report of annotations needing a person's attention is built from.
    """
    for properties in PostgresSamplePropertiesRepository(connection).list_for_module(annotation.occurrence.module_hash):
        if properties.occurrence == annotation.occurrence:
            return properties.sample_hash

    return None


def _lowest_occurrence(properties: list[TrackerSampleProperties]) -> TrackerSampleProperties:
    return min(
        properties,
        key=lambda item: (item.occurrence.module_hash, item.occurrence.instrument_index, item.occurrence.sample_slot),
    )
