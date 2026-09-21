from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from samplecore.models.base import FROZEN

DESCRIPTOR_SIZE: Final[int] = 512
DEFAULT_WIDTH: Final[int] = 32
DEFAULT_STAGE_COUNT: Final[int] = 4


class DescriptorShape(BaseModel):
    """The dimensions that fix a descriptor network, recorded beside its weights."""

    model_config = FROZEN

    band_count: int
    time_columns: int
    width: int = DEFAULT_WIDTH
    stage_count: int = DEFAULT_STAGE_COUNT
    embedding_size: int = DESCRIPTOR_SIZE
