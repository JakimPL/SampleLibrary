from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import ModuleHash, SampleHash


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


class ModuleCloudCoordinate(BaseModel):
    """Where one Module sits in the library's 2D embedding space, as of one embedding run.

    Today's positions come from `samplecloud.placeholder_modules`, seeded from a module's own hash
    rather than a genuine similarity fit -- standing in until a spectral-distance metric makes a
    real per-module embedding possible. A later run's coordinate for a given hash entirely replaces
    an earlier one, mirroring SampleCloudCoordinate's own replacement semantics.
    """

    model_config = FROZEN

    module_hash: ModuleHash
    x: float
    y: float
    computed_at: datetime
