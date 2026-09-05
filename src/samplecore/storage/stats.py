from __future__ import annotations

import duckdb

from samplecore.models.relation import RelationType
from samplecore.models.stats import LibraryStats, RelationTypeCount, TrackerModuleCount
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.sample import DuckDBSampleRepository


def compute_library_stats(connection: duckdb.DuckDBPyConnection) -> LibraryStats:
    """A snapshot of the catalog's overall size and composition, computed directly from storage.

    ``total_stored_bytes`` sums each Sample's own ``stored_bytes`` property rather than
    recomputing that byte-size formula in SQL, so the two never drift apart.
    """
    module_count = _scalar(connection, "SELECT count(*) FROM module")
    sample_properties_count = _scalar(connection, "SELECT count(*) FROM sample_properties")
    samples = DuckDBSampleRepository(connection).list_all()

    modules_by_tracker = tuple(
        TrackerModuleCount(tracker=TrackerFormat(tracker), module_count=count)
        for tracker, count in connection.execute("SELECT tracker, count(*) FROM module GROUP BY tracker").fetchall()
    )
    relations_by_type = tuple(
        RelationTypeCount(relation_type=RelationType(relation_type), relation_count=count)
        for relation_type, count in connection.execute(
            "SELECT relation_type, count(*) FROM sample_relation GROUP BY relation_type"
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


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    assert row is not None
    return int(row[0])
