from __future__ import annotations

from sqlalchemy import Connection, func, select

from samplecore.models.relation import RelationType
from samplecore.models.stats import LibraryStats, RelationTypeCount, TrackerModuleCount
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import module, sample_properties, sample_relation
from samplecore.storage.repositories.sample import PostgresSampleRepository


def compute_library_stats(connection: Connection) -> LibraryStats:
    """A snapshot of the catalog's overall size and composition, computed directly from storage.

    ``total_stored_bytes`` sums each Sample's own ``stored_bytes`` property rather than
    recomputing that byte-size formula in SQL, so the two never drift apart.
    """
    # func.count() is SQLAlchemy's dynamically-generated SQL COUNT(*), not a plain Python callable --
    # pylint cannot see through func's proxy attribute access, so every call below is a false positive.
    # pylint: disable-next=not-callable
    module_count = connection.execute(select(func.count()).select_from(module)).scalar_one()
    # pylint: disable-next=not-callable
    sample_properties_count = connection.execute(select(func.count()).select_from(sample_properties)).scalar_one()
    samples = PostgresSampleRepository(connection).list_all()

    modules_by_tracker = tuple(
        TrackerModuleCount(tracker=TrackerFormat(row.tracker), module_count=row.module_count)
        for row in connection.execute(
            # pylint: disable-next=not-callable
            select(module.c.tracker, func.count().label("module_count")).group_by(module.c.tracker)
        ).fetchall()
    )
    relations_by_type = tuple(
        RelationTypeCount(relation_type=RelationType(row.relation_type), relation_count=row.relation_count)
        for row in connection.execute(
            # pylint: disable-next=not-callable
            select(sample_relation.c.relation_type, func.count().label("relation_count")).group_by(
                sample_relation.c.relation_type
            )
        ).fetchall()
    )

    return LibraryStats(
        module_count=module_count,
        sample_count=len(samples),
        sample_properties_count=sample_properties_count,
        modules_by_tracker=modules_by_tracker,
        relations_by_type=relations_by_type,
        total_stored_bytes=sum(sample.stored_bytes for sample in samples),
    )
