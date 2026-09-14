from __future__ import annotations

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Any, Final

from pydantic import BaseModel, StringConstraints

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, SampleHash

# An experiment extracted by a descriptor this project trained names the stored model it read,
# so the extractor that produced its vectors can be rebuilt from the row alone. A scoring of
# label suggestions is an experiment too, holding suggestions in place of vectors, and it names
# the vocabulary it ranked in order, which is what gives each suggested tag a lasting rank.
LEARNED_BACKEND_NAME: Final[str] = "learned"
ZERO_SHOT_BACKEND_NAME: Final[str] = "zero_shot"
MODEL_PARAMETER: Final[str] = "model"
VOCABULARY_PARAMETER: Final[str] = "vocabulary"
READING_PARAMETER: Final[str] = "reading"
CHECKPOINT_REVISION_PARAMETER: Final[str] = "checkpoint_revision"
EXPERIMENT_KEY_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9._-]{0,127}$"

# The name a person or a pipeline refers to one experiment by again: lower case letters, digits and
# a few separators, short enough to sit in a file or a unit name as it is.
ExperimentKey = Annotated[str, StringConstraints(pattern=EXPERIMENT_KEY_PATTERN)]


@unique
class Reading(StrEnum):
    """How a pass reads a stored sample before an extractor hears it, recorded on the experiment it fills.

    `NOMINAL` reads the frames at the rate the store writes, the reading every cloud so far was
    built on. `HEARD_RATE` reads them at the rate the library plays the sample at, so a bass played
    two octaves below its file's rate reaches the extractor as a bass.
    """

    NOMINAL = "nominal"
    HEARD_RATE = "heard_rate"


class Experiment(BaseModel):
    """One embedding run's identity: which FeatureExtractor backend produced it, and when.

    Every feature vector in ``sample_feature_vector`` belongs to exactly one Experiment, so two
    backends -- or two runs of the same backend with different parameters -- can be extracted
    concurrently without either overwriting the other's output. Comparing them, or promoting one to
    ``sample_cloud_coordinates``, is a later, deliberate step that reads a chosen experiment's own
    vectors, not something extraction itself needs to coordinate. A key files the experiment under a
    name of its own, unique across the catalog, which is how a command run again finds the
    experiment it made the first time.
    """

    model_config = FROZEN

    id: Index
    backend_name: str
    params: dict[str, Any]
    created_at: datetime
    label: str | None = None
    key: ExperimentKey | None = None


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
