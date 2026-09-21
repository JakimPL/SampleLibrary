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


class MorphPair(BaseModel):
    """Two samples ready to be morphed: which two, the rate each is heard at, and the file each is read from.

    A morph puts both samples in one frame, which the two rates alone fix, so they travel with the
    pair: the process reading it needs no catalog. ``first_file`` and ``second_file`` name the sample
    file an end found in a sample directory is read from, and stay empty for an end the store holds
    an object of. Everything a pair says holds for every point between the two, which is what lets a
    filter between them be asked for once and applied at any weight.
    """

    model_config = FROZEN

    first: SampleHash
    second: SampleHash
    first_rate_hz: Rate
    second_rate_hz: Rate
    first_file: Path | None = None
    second_file: Path | None = None


class HeardMorphPoint(MorphPair):
    """One point between two samples heard in their own frame: the pair, and how far along it the point stands.

    A render is named by the weight the way it is named by the pair, so two requests for one point
    name one render.
    """

    weight: float = Field(ge=0.0, le=1.0, multiple_of=1 / MORPH_WEIGHT_STEPS)

    @property
    def step(self) -> int:
        """Which step of the grid the weight sits on, from 0 at the first sample."""
        return int(round(self.weight * MORPH_WEIGHT_STEPS))

    @property
    def pair(self) -> MorphPair:
        """The two samples this point stands between, apart from where along them it stands."""
        return MorphPair(
            first=self.first,
            second=self.second,
            first_rate_hz=self.first_rate_hz,
            second_rate_hz=self.second_rate_hz,
            first_file=self.first_file,
            second_file=self.second_file,
        )


def morph_weights() -> tuple[float, ...]:
    """Every weight a morph can be asked for, from the first sample to the second."""
    return tuple(step / MORPH_WEIGHT_STEPS for step in range(MORPH_WEIGHT_STEPS + 1))


class MorphServiceStatus(BaseModel):
    """What an inference process serves: the name of the route it renders through, and the fingerprint its renders are named by.

    `name` tells the excitation, the timeline and the glide the route renders with apart, and
    `description` says everything the route reads. The fingerprint follows the description, so a
    render's cache identity changes with what renders it and with nothing else.
    """

    model_config = FROZEN

    name: str
    fingerprint: str
    weight_steps: int
    description: dict[str, JsonValue]
