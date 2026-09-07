from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, SampleHash


class Experiment(BaseModel):
    """One embedding run's identity: which FeatureExtractor backend produced it, and when.

    Every feature vector in ``sample_feature_vector`` belongs to exactly one Experiment, so two
    backends -- or two runs of the same backend with different parameters -- can be extracted
    concurrently without either overwriting the other's output. Comparing them, or promoting one to
    ``sample_cloud_coordinates``, is a later, deliberate step that reads a chosen experiment's own
    vectors, not something extraction itself needs to coordinate.
    """

    model_config = FROZEN

    id: Index
    backend_name: str
    params: dict[str, Any]
    created_at: datetime
    label: str | None = None


class SampleFeatureVector(BaseModel):
    """One Sample's raw extractor output, as of one experiment's run.

    Distinct from ``SampleSpectralFeature``: this holds a ``FeatureExtractor``'s direct output for
    one named experiment, not the standardized vector a promoted experiment's UMAP fit was computed
    from -- the two stay separate tables and separate models for that reason.
    """

    model_config = FROZEN

    experiment_id: Index
    sample_hash: SampleHash
    vector: tuple[float, ...]
    computed_at: datetime
