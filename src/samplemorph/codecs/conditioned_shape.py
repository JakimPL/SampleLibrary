from __future__ import annotations

import math
from enum import StrEnum
from typing import Final

from pydantic import BaseModel

from samplecore.models.base import FROZEN


class ResidualLayout(StrEnum):
    """How the residual is laid out at the bottleneck.

    `VECTOR` reads the whole bottleneck into one vector, so every residual number can speak for any
    band at any moment. `MAP` keeps the bottleneck's map and holds a few numbers at each of its
    cells, so a residual number speaks for the bands and the moment of the cell it sits in.
    """

    VECTOR = "vector"
    MAP = "map"


DEFAULT_RESIDUAL_SIZE: Final[int] = 64
DEFAULT_RESIDUAL_LAYOUT: Final[ResidualLayout] = ResidualLayout.VECTOR
DEFAULT_CODEC_WIDTH: Final[int] = 16
STAGE_COUNT: Final[int] = 4
BAND_STRIDE: Final[int] = 4
TIME_STRIDES: Final[tuple[int, ...]] = (1, 2, 2, 2)


class ConditionedCodecShape(BaseModel):
    """The dimensions that fix a conditioned codec, recorded beside its weights.

    `residual_size` counts the numbers the residual holds at each of its positions: the vector
    layout has one position, the map layout one per bottleneck cell.
    """

    model_config = FROZEN

    band_count: int
    time_columns: int
    descriptor_size: int
    residual_size: int = DEFAULT_RESIDUAL_SIZE
    width: int = DEFAULT_CODEC_WIDTH
    layout: ResidualLayout = DEFAULT_RESIDUAL_LAYOUT

    @property
    def band_stride(self) -> int:
        return int(BAND_STRIDE**STAGE_COUNT)

    @property
    def padded_band_count(self) -> int:
        """The band axis rounded up to what the stages divide evenly, the extra rows resting on silence."""
        return -(-self.band_count // self.band_stride) * self.band_stride

    @property
    def bottleneck_shape(self) -> tuple[int, int, int]:
        """(channels, bands, columns) at the narrowest stage."""
        columns = self.time_columns
        for stride in TIME_STRIDES:
            columns //= stride
        return self.width * 2 ** (STAGE_COUNT - 1), self.padded_band_count // self.band_stride, columns

    @property
    def residual_shape(self) -> tuple[int, ...]:
        """The residual's own axes: `(residual_size,)` as a vector, `(residual_size, bands, columns)` as a map."""
        if self.layout is ResidualLayout.MAP:
            _channels, bands, columns = self.bottleneck_shape
            return self.residual_size, bands, columns
        return (self.residual_size,)

    @property
    def residual_length(self) -> int:
        """How many numbers the residual holds once flattened, which is what a latent carries."""
        return math.prod(self.residual_shape)
