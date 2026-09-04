from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, SampleHash


@unique
class RelationType(StrEnum):
    """The kind of near-duplicate link two distinct Samples can be proposed to share."""

    BIT_DEPTH_VARIANT = "bit_depth_variant"
    RESAMPLED_VARIANT = "resampled_variant"


class RelationReview(BaseModel):
    """A curator's verdict on an automatically proposed SampleRelation, once one has been made."""

    model_config = FROZEN

    confirmed: bool
    reviewed_at: datetime
    reviewed_by: str


class SampleRelation(BaseModel):
    """One automatically detected, optionally curator-reviewed link between two Samples.

    ``subject_hash`` is always the lexicographically smaller of the two hashes, so the same pair,
    found by two different detection methods or in either order, always lands on the same identity
    for review purposes; ``method`` still lets independent detectors each record their own row for
    the same pair, so agreement between methods is itself visible corroborating evidence rather
    than being collapsed away.
    """

    model_config = FROZEN

    id: Index
    subject_hash: SampleHash
    reference_hash: SampleHash
    relation_type: RelationType
    method: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: dict[str, float]
    detected_at: datetime
    review: RelationReview | None = None

    @model_validator(mode="after")
    def _distinct_and_ordered(self) -> SampleRelation:
        if self.subject_hash == self.reference_hash:
            raise ValueError("a sample cannot be related to itself")
        if self.subject_hash > self.reference_hash:
            raise ValueError("subject_hash must be the lexicographically smaller of the two hashes")

        return self
