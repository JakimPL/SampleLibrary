from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from samplecore.labeling.labels import canonical_label
from samplecore.models.base import FROZEN
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.scalars import Rating, SampleHash

# One spelling per label wherever it was typed: a label is stored as it is compared and displayed, and
# "warm pad", "Warm Pad" and "WARM:PAD" name what "WARM PAD" and "WARM: PAD" do to the person who wrote them.
LabelText = Annotated[str, AfterValidator(canonical_label)]


@unique
class AnnotationSource(StrEnum):
    """Whether an annotation was made for one sample or applied to a whole equivalence class."""

    SAMPLE = "sample"
    EQUIVALENCE_CLASS = "equivalence_class"


@unique
class AnchorKind(StrEnum):
    """Where an annotated sample was found: a module slot, or a file of a sample directory."""

    MODULE_SLOT = "module_slot"
    SAMPLE_FILE = "sample_file"


class ModuleSlotAnchor(BaseModel):
    """The module slot an annotation stays findable through, with the names a person recognizes it by.

    Reading the current hash out of the slot is what relinks the annotation to its sample.
    ``module_filename`` and ``sample_name`` are the same anchor in human-readable form, for the case
    where even the module is no longer recognized.
    """

    model_config = FROZEN

    kind: Literal[AnchorKind.MODULE_SLOT] = AnchorKind.MODULE_SLOT
    occurrence: SampleOccurrence
    module_filename: str
    sample_name: str


class SampleFileAnchor(BaseModel):
    """The sample file an annotation stays findable through, whose path a person recognizes as it is.

    Reading the sample the catalog holds for that file today is what relinks the annotation.
    """

    model_config = FROZEN

    kind: Literal[AnchorKind.SAMPLE_FILE] = AnchorKind.SAMPLE_FILE
    location: SampleFileLocation


AnnotationAnchor = Annotated[ModuleSlotAnchor | SampleFileAnchor, Field(discriminator="kind")]


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

    @property
    def decisions(self) -> AnnotationDecisions:
        """The three decisions alone, apart from whatever else a subclass records beside them."""
        return AnnotationDecisions(label=self.label, rating=self.rating, favorite=self.favorite)


NO_DECISIONS: Final[AnnotationDecisions] = AnnotationDecisions(label=None, rating=None, favorite=False)


@unique
class AnnotationDecision(StrEnum):
    """One of the three things a person can decide about a sample, named the way a request names it."""

    LABEL = "label"
    RATING = "rating"
    FAVORITE = "favorite"


class AnnotationChanges(BaseModel):
    """What one gesture changes about a sample: the decisions it names, each with the value it takes.

    A star click changes the rating alone, so a sample keeps the label another gesture gave it a
    moment earlier, and a group gesture keeps every member's own say on the decisions it leaves
    alone. The values of decisions outside ``changed`` are carried along and read by nothing.
    """

    model_config = FROZEN

    values: AnnotationDecisions
    changed: frozenset[AnnotationDecision]

    def applied_to(self, current: AnnotationDecisions) -> AnnotationDecisions:
        """The decisions a sample holds once this change lands on what it holds now."""
        label, rating, favorite = current.label, current.rating, current.favorite
        for decision in self.changed:
            match decision:
                case AnnotationDecision.LABEL:
                    label = self.values.label
                case AnnotationDecision.RATING:
                    rating = self.values.rating
                case AnnotationDecision.FAVORITE:
                    favorite = self.values.favorite
        return AnnotationDecisions(label=label, rating=rating, favorite=favorite)


class SampleAnnotation(AnnotationDecisions):
    """What a person decided about one sample, together with where that sample was found.

    A row exists because at least one decision was made, which the validator below and the table's
    own CHECK both hold to. Taking back the last of them removes the row.

    An anchor travels with every annotation so a sample stays findable when its hash changes -- the
    module slot or the sample file it was found in, whose current sample is what the annotation
    relinks to, which is the whole reason it is worth more than the hash it happens to carry today.

    `source` keeps the difference between a sample a person listened to individually and one that
    inherited its annotation from the near-duplicates it was grouped with, since that distinction
    matters to anything later trained on these decisions.
    """

    sample_hash: SampleHash
    anchor: AnnotationAnchor
    source: AnnotationSource
    annotated_at: datetime

    @model_validator(mode="after")
    def _requires_a_decision(self) -> Self:
        if not self.records_a_decision:
            raise ValueError("an annotation records a label, a rating or a favorite mark")

        return self


class AnnotationImport(BaseModel):
    """A labels file read into the catalog: the digest of its bytes, how many annotations it held, and when.

    The same bytes read twice are one import, taken again at the later time, so whether a library
    already holds what a file says is one lookup by the file's digest.
    """

    model_config = FROZEN

    file_sha256: str = Field(min_length=64, max_length=64)
    annotation_count: int = Field(ge=0)
    imported_at: datetime
