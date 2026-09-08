from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection

from samplecore.models.annotation import AnnotationDecisions, AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository


def anchored_annotations(
    connection: Connection,
    *,
    sample_hashes: tuple[str, ...],
    decisions: AnnotationDecisions,
    source: AnnotationSource,
    annotated_at: datetime,
) -> tuple[SampleAnnotation, ...]:
    """One annotation per sample, each anchored to a module slot it stays findable through.

    A sample's hash depends on how this project hashes audio, so an annotation keyed on the hash
    alone would be lost the moment that changes. The anchor is the occurrence lowest in
    ``(module_hash, instrument_index, sample_slot)`` order -- a deterministic choice, so revisiting
    the same sample keeps naming the same slot -- recorded together with the module's filename and
    the occurrence's name, which stay readable to a person even when neither hash resolves.

    Only samples the catalog holds an occurrence for come back, an occurrence being the anchor's
    whole source. A caller writing a whole group takes the samples left out as the ones whose
    annotation it should remove, so a group ends up saying one thing throughout.
    """
    properties_repository = PostgresSamplePropertiesRepository(connection)
    anchor_by_hash = {
        sample_hash: _lowest_occurrence(properties_repository.list_for_sample(sample_hash))
        for sample_hash in sample_hashes
    }
    anchored = {sample_hash: anchor for sample_hash, anchor in anchor_by_hash.items() if anchor is not None}
    module_hashes = sorted({anchor.occurrence.module_hash for anchor in anchored.values()})
    modules_by_hash = PostgresModuleRepository(connection).get_many(module_hashes)

    return tuple(
        SampleAnnotation(
            sample_hash=sample_hash,
            label=decisions.label,
            rating=decisions.rating,
            favorite=decisions.favorite,
            occurrence=anchor.occurrence,
            module_filename=modules_by_hash[anchor.occurrence.module_hash].filename,
            sample_name=anchor.name,
            source=source,
            annotated_at=annotated_at,
        )
        for sample_hash, anchor in anchored.items()
    )


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


def _lowest_occurrence(properties: tuple[TrackerSampleProperties, ...]) -> TrackerSampleProperties | None:
    return min(
        properties,
        key=lambda item: (item.occurrence.module_hash, item.occurrence.instrument_index, item.occurrence.sample_slot),
        default=None,
    )
