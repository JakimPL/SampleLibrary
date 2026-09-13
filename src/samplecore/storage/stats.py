from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Row, func, select
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType
from samplecore.models.stats import LibraryStats, RelationTypeCount, TrackerModuleCount
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import module, sample, sample_properties, sample_relation


def compute_library_stats(connection: Connection) -> LibraryStats:
    """A snapshot of the catalog's overall size and composition, computed directly from storage.

    ``total_stored_bytes`` is gathered per depth-and-layout group -- a handful of rows over the whole
    catalog -- and each group's frames are then multiplied out through `Sample.stored_bytes`'s own
    formula, so the byte size a listing shows and the one this reports can never drift apart while
    the count itself stays a database aggregate rather than a hundred thousand models built to be
    summed.
    """
    # func.count() is SQLAlchemy's dynamically-generated SQL COUNT(*), not a plain Python callable --
    # pylint cannot see through func's proxy attribute access, so every call below is a false positive.
    # pylint: disable-next=not-callable
    module_count = connection.execute(select(func.count()).select_from(module)).scalar_one()
    # pylint: disable-next=not-callable
    sample_properties_count = connection.execute(select(func.count()).select_from(sample_properties)).scalar_one()
    shapes = connection.execute(
        select(
            sample.c.depth,
            sample.c.channels,
            # pylint: disable-next=not-callable
            func.count().label("sample_count"),
            func.sum(sample.c.frames).label("total_frames"),
        ).group_by(sample.c.depth, sample.c.channels)
    ).fetchall()

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
        sample_count=sum(shape.sample_count for shape in shapes),
        sample_properties_count=sample_properties_count,
        modules_by_tracker=modules_by_tracker,
        relations_by_type=relations_by_type,
        total_stored_bytes=sum(_stored_bytes_of(shape) for shape in shapes),
    )


def _stored_bytes_of(shape: Row[Any]) -> int:
    """How many bytes every sample of one depth and channel layout occupies together."""
    total_frames: int = shape.total_frames
    return total_frames * ChannelLayout(shape.channels) * BitDepth(shape.depth).bytes_per_frame
