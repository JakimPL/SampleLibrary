from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, JsonValue
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash

MORPH_WEIGHT_STEPS: Final[int] = 100


class MorphPoint(BaseModel):
    """One point between two samples: which two, and how far from the first toward the second.

    The weight lies on a grid of hundredths, so every point a slider can ask for writes as one
    two-place decimal in a URL and names exactly one cached render.
    """

    model_config = FROZEN

    first: SampleHash
    second: SampleHash
    weight: float = Field(ge=0.0, le=1.0, multiple_of=1 / MORPH_WEIGHT_STEPS)

    @property
    def step(self) -> int:
        """Which step of the grid the weight sits on, from 0 at the first sample."""
        return int(round(self.weight * MORPH_WEIGHT_STEPS))


class HeardMorphPoint(MorphPoint):
    """A point between two samples with the rate each end is heard at, and the file each end is read from.

    A render puts both samples in one frame, which the two rates alone fix, so they travel with the
    point: the process rendering it needs no catalog, and a render is named by them the way it is
    named by the weight. ``first_file`` and ``second_file`` name the sample file an end found in a
    sample directory is read from, and stay empty for an end the store holds an object of.
    """

    first_rate_hz: Rate
    second_rate_hz: Rate
    first_file: Path | None = None
    second_file: Path | None = None


def morph_weights() -> tuple[float, ...]:
    """Every weight a morph can be asked for, from the first sample to the second."""
    return tuple(step / MORPH_WEIGHT_STEPS for step in range(MORPH_WEIGHT_STEPS + 1))


class MorphServiceStatus(BaseModel):
    """What an inference process serves: the route it renders through, the device it runs on, and the fingerprint its renders are named by.

    `route` is the route's kind and `name` tells the routes of one kind apart; `description` says
    everything the route reads, its settings or the stored model and the files it was loaded from,
    the way a listening set's manifest does. The fingerprint follows the description, so a render's
    cache identity changes with what renders it and with nothing else.
    """

    model_config = FROZEN

    route: str
    name: str
    device: str
    fingerprint: str
    weight_steps: int
    description: dict[str, JsonValue]
