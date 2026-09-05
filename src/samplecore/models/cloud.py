from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash


class SampleCloudCoordinate(BaseModel):
    """Where one Sample sits in the library's 2D embedding space, as of one embedding run.

    A full embedding run recomputes every sample's position at once -- UMAP has no natural
    per-point incremental update -- so a later run's coordinate for a given hash entirely replaces
    an earlier one, rather than the two ever coexisting.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    x: float
    y: float
    computed_at: datetime
