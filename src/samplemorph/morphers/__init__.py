from __future__ import annotations

from typing import Protocol, Self

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplemorph.images import SampleLatent


class MorphWeights(BaseModel):
    """How far a morph has travelled from the first sample toward the second.

    The latent and the conditioners carry their own weights, so timbre can travel while pitch stays
    put, or pitch can glide while timbre stays put. Holding them apart is most of what makes a
    result musical rather than a wash.
    """

    model_config = FROZEN

    latent: float = Field(ge=0.0, le=1.0)
    conditioners: float = Field(ge=0.0, le=1.0)

    @classmethod
    def uniform(cls, weight: float) -> Self:
        """Both halves travelling together, the plain reading of "halfway between"."""
        return cls(latent=weight, conditioners=weight)


class Morpher(Protocol):
    """Combines two encoded samples at a chosen weight into one.

    An implementation returns a latent that decodes to a single sound. A result that decodes to
    both sounds playing at once is a dissolve rather than a morph, which is the outcome this
    project has already built once and rejected.
    """

    def morph(self, first: SampleLatent, second: SampleLatent, *, weights: MorphWeights) -> SampleLatent: ...
