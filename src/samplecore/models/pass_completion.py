from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DIGEST_LENGTH: Final[int] = 64


@unique
class PassKind(StrEnum):
    """A pass over the whole library that records when it last finished, and over what."""

    MODULES = "modules"
    NOTES = "notes"
    EQUIVALENCE = "equivalence"


class PassCompletion(BaseModel):
    """What a pass had in front of it the last time it finished completely: a digest of its input, and when.

    A pass finding the same digest in front of it again would come out the same, so it ends there
    with nothing to do. The record lives beside what the pass wrote, so emptying the catalog
    forgets it along with the rows it describes.
    """

    model_config = FROZEN

    kind: PassKind
    digest: str = Field(min_length=DIGEST_LENGTH, max_length=DIGEST_LENGTH)
    completed_at: datetime
