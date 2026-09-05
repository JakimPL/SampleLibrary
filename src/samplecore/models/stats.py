from __future__ import annotations

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.relation import RelationType
from samplecore.models.scalars import Count
from samplecore.models.tracker import TrackerFormat


class TrackerModuleCount(BaseModel):
    """How many catalogued modules belong to one tracker format."""

    model_config = FROZEN

    tracker: TrackerFormat
    module_count: Count


class RelationTypeCount(BaseModel):
    """How many detected equivalence-class links belong to one relation type."""

    model_config = FROZEN

    relation_type: RelationType
    relation_count: Count


class LibraryStats(BaseModel):
    """A snapshot of the catalog's overall size and composition."""

    model_config = FROZEN

    module_count: Count
    sample_count: Count
    sample_properties_count: Count
    modules_by_tracker: tuple[TrackerModuleCount, ...]
    relations_by_type: tuple[RelationTypeCount, ...]
    total_stored_bytes: Count
