from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection

from samplecore.models.label import LabelSource, SampleLabel
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository


def anchored_labels(
    connection: Connection,
    *,
    sample_hashes: tuple[str, ...],
    label: str,
    source: LabelSource,
    labeled_at: datetime,
) -> tuple[SampleLabel, ...]:
    """One label per sample, each anchored to a module slot it stays findable through.

    A sample's hash depends on how this project hashes audio, so a label keyed on the hash alone
    would be lost the moment that changes. The anchor is the occurrence lowest in
    ``(module_hash, instrument_index, sample_slot)`` order -- a deterministic choice, so relabeling
    the same sample keeps naming the same slot -- recorded together with the module's filename and
    the occurrence's name, which stay readable to a person even when neither hash resolves.

    Only samples the catalog holds an occurrence for come back, an occurrence being the anchor's
    whole source.
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
        SampleLabel(
            sample_hash=sample_hash,
            label=label,
            occurrence=anchor.occurrence,
            module_filename=modules_by_hash[anchor.occurrence.module_hash].filename,
            sample_name=anchor.name,
            source=source,
            labeled_at=labeled_at,
        )
        for sample_hash, anchor in anchored.items()
    )


def relinked_hash(connection: Connection, label: SampleLabel) -> str | None:
    """The hash the labeled module slot holds now, for a label whose sample has been rehashed.

    Reads the anchor back through the catalog: the module is found by its own hash, and the slot it
    names gives whatever sample sits there today. ``None`` where the module or the slot is no longer
    cataloged, which is what a report of labels needing a person's attention is built from.
    """
    for properties in PostgresSamplePropertiesRepository(connection).list_for_module(label.occurrence.module_hash):
        if properties.occurrence == label.occurrence:
            return properties.sample_hash

    return None


def _lowest_occurrence(properties: tuple[TrackerSampleProperties, ...]) -> TrackerSampleProperties | None:
    return min(
        properties,
        key=lambda item: (item.occurrence.module_hash, item.occurrence.instrument_index, item.occurrence.sample_slot),
        default=None,
    )
