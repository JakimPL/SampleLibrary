from __future__ import annotations

from math import ceil
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN

DEFAULT_LATENT_SIZE: Final[int] = 128
DEFAULT_FEATURE_WIDTH: Final[int] = 32
DEFAULT_FEATURE_STAGE_COUNT: Final[int] = 4
CHANNELS_PER_GROUP: Final[int] = 4


class FeatureShape(BaseModel):
    """The dimensions that fix a feature autoencoder and its critic, recorded beside their weights.

    Every stage halves both axes of the grid, so a grid is padded up to a whole number of
    `2 ** stage_count` along each, and the deepest map, flattened, is what the latent is read from.
    Channels double at every stage from `width`, grouped `CHANNELS_PER_GROUP` to a normalization.
    """

    model_config = FROZEN

    band_count: int = Field(ge=1)
    time_columns: int = Field(ge=1)
    latent_size: int = Field(default=DEFAULT_LATENT_SIZE, ge=1)
    width: int = Field(default=DEFAULT_FEATURE_WIDTH, ge=CHANNELS_PER_GROUP, multiple_of=CHANNELS_PER_GROUP)
    stage_count: int = Field(default=DEFAULT_FEATURE_STAGE_COUNT, ge=1)

    @property
    def reduction(self) -> int:
        """How many cells of the grid one cell of the deepest map stands for along each axis."""
        return int(2**self.stage_count)

    @property
    def padded_band_count(self) -> int:
        return ceil(self.band_count / self.reduction) * self.reduction

    @property
    def padded_time_columns(self) -> int:
        return ceil(self.time_columns / self.reduction) * self.reduction

    @property
    def deepest_channels(self) -> int:
        return int(self.width * 2 ** (self.stage_count - 1))

    @property
    def deepest_map(self) -> tuple[int, int, int]:
        """The deepest map as (channels, bands, columns)."""
        return (
            self.deepest_channels,
            self.padded_band_count // self.reduction,
            self.padded_time_columns // self.reduction,
        )

    @property
    def deepest_size(self) -> int:
        channels, bands, columns = self.deepest_map
        return channels * bands * columns
