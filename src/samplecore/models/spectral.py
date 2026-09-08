from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash


class SampleSpectralFeature(BaseModel):
    """The standardized timbral feature vector one Sample was embedded from, as of one embedding run.

    ``vector`` holds the same post-``StandardScaler`` values `samplecloud.reduce` fits its UMAP
    projection from, so two samples' vectors are directly comparable by Euclidean distance without
    re-deriving or re-fetching any standardization statistics. A full embedding run recomputes
    every sample's vector at once, mirroring `SampleCloudCoordinate`'s own full-replace semantics.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    vector: tuple[float, ...]
    computed_at: datetime
