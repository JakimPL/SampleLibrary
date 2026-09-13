from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, model_validator

from samplecore.models.base import FROZEN
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.scalars import Rating, SampleHash

# Upper case, so one wording is one label wherever it was typed: a label is stored as it is compared
# and displayed, and "warm pad" and "Warm Pad" name the same thing to the person who wrote them.
LabelText = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1)]


@unique
class AnnotationSource(StrEnum):
    """Whether an annotation was made for one sample or applied to a whole equivalence class."""

    SAMPLE = "sample"
    EQUIVALENCE_CLASS = "equivalence_class"


class AnnotationDecisions(BaseModel):
    """The three things a person can decide about a sample.

    The label says what the sample is, as free text: it records what a listener actually decided,
    ahead of any vocabulary being settled, so it stays unconstrained by `SampleCategory`'s fourteen
    guessed roles and wins wherever it exists. It is kept in upper case, which is the case it is
    shown in, so the vocabulary a person builds by habit collects one entry per wording. The rating and the favorite mark say what the
    listener thought of it, which is what turns browsing the library into a collection of a person's
    own.

    Any one of them may stand alone, and all three may be empty: an empty set of decisions is how a
    person takes back everything they had said about a sample.
    """

    model_config = FROZEN

    label: LabelText | None
    rating: Rating | None
    favorite: bool

    @property
    def records_a_decision(self) -> bool:
        """Whether anything at all is being said about the sample."""
        return self.label is not None or self.rating is not None or self.favorite


class SampleAnnotation(AnnotationDecisions):
    """What a person decided about one sample, together with where that sample was found.

    A row exists because at least one decision was made, which the validator below and the table's
    own CHECK both hold to. Taking back the last of them removes the row.

    An occurrence travels with every annotation so a sample stays findable when its hash changes --
    reading the current hash out of that module slot is what relinks the annotation to its sample,
    which is the whole reason it is worth more than the hash it happens to carry today.
    `module_filename` and `sample_name` are the same anchor in human-readable form, for the case
    where even the module is no longer recognized.

    `source` keeps the difference between a sample a person listened to individually and one that
    inherited its annotation from the near-duplicates it was grouped with, since that distinction
    matters to anything later trained on these decisions.
    """

    sample_hash: SampleHash
    occurrence: SampleOccurrence
    module_filename: str
    sample_name: str
    source: AnnotationSource
    annotated_at: datetime

    @model_validator(mode="after")
    def _requires_a_decision(self) -> Self:
        if not self.records_a_decision:
            raise ValueError("an annotation records a label, a rating or a favorite mark")

        return self
