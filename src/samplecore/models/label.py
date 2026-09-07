from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from samplecore.models.base import FROZEN
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.scalars import SampleHash

LabelText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


@unique
class LabelSource(StrEnum):
    """Whether a hand label was chosen for one sample or applied to a whole equivalence class."""

    SAMPLE = "sample"
    EQUIVALENCE_CLASS = "equivalence_class"


class SampleLabel(BaseModel):
    """A category a person chose for one sample, together with where that sample was found.

    The category is free text: this records what a listener actually decided, ahead of any
    vocabulary being settled, so it is deliberately unconstrained by `SampleCategory`'s fourteen
    guessed roles. A hand label is authoritative wherever it exists.

    An occurrence travels with every label so a sample stays findable when its hash changes --
    reading the current hash out of that module slot is what relinks the label to its sample, which
    is the whole reason a label is worth more than the hash it happens to carry today.
    `module_filename` and `sample_name` are the same anchor in human-readable form, for the case
    where even the module is no longer recognised.

    `source` keeps the difference between a sample a person listened to individually and one that
    inherited its label from the near-duplicates it was grouped with, since that distinction matters
    to anything later trained on these labels.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    label: LabelText
    occurrence: SampleOccurrence
    module_filename: str
    sample_name: str
    source: LabelSource
    labeled_at: datetime
