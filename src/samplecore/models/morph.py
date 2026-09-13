from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field, field_validator
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash

MORPH_WEIGHT_STEPS: Final[int] = 16


class MorphPoint(BaseModel):
    """One point between two samples: which two, and how far from the first toward the second.

    The weight lies on a grid of sixteenths, so every point a slider can ask for is exact in
    binary, writes as one short decimal in a URL, and names exactly one cached render.
    """

    model_config = FROZEN

    first: SampleHash
    second: SampleHash
    weight: float = Field(ge=0.0, le=1.0)

    @field_validator("weight")
    @classmethod
    def on_the_grid(cls, weight: float) -> float:
        """Keep the weight to the grid of sixteenths.

        Raises:
            ValueError: the weight lies between two steps of the grid.
        """
        if not (weight * MORPH_WEIGHT_STEPS).is_integer():
            raise ValueError(f"a morph weight is a multiple of 1/{MORPH_WEIGHT_STEPS}, got {weight}")
        return weight

    @property
    def step(self) -> int:
        """Which step of the grid the weight sits on, from 0 at the first sample."""
        return int(round(self.weight * MORPH_WEIGHT_STEPS))


class HeardMorphPoint(MorphPoint):
    """A point between two samples with the rate each end is heard at.

    A render puts both samples in one frame, which the two rates alone fix, so they travel with the
    point: the process rendering it needs no catalog, and a render is named by them the way it is
    named by the weight.
    """

    first_rate_hz: Rate
    second_rate_hz: Rate


def morph_weights() -> tuple[float, ...]:
    """Every weight a morph can be asked for, from the first sample to the second."""
    return tuple(step / MORPH_WEIGHT_STEPS for step in range(MORPH_WEIGHT_STEPS + 1))


class MorphServiceStatus(BaseModel):
    """What an inference process serves: the model, the route it renders through, and the device it runs on.

    The fingerprint names the exact model files loaded, so a render's cache identity changes with
    the model and with nothing else.
    """

    model_config = FROZEN

    model: str
    codec: str
    canonicalizer: str
    latent_size: int
    vocoder: str
    restorer: str | None
    device: str
    fingerprint: str
    weight_steps: int
