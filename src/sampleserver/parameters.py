from __future__ import annotations

from typing import Annotated, Final

from fastapi import Path as RoutePath
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SAMPLE_HASH_PATTERN

MAX_PAGE_OFFSET: Final[int] = 2**63 - 1

SampleHashPath = Annotated[str, RoutePath(pattern=SAMPLE_HASH_PATTERN)]
ModuleHashPath = Annotated[str, RoutePath(pattern=SAMPLE_HASH_PATTERN)]


class ErrorDetail(BaseModel):
    """What a refused request is told, in the one shape every route answers a refusal in."""

    model_config = FROZEN

    detail: str


NOT_FOUND_RESPONSE: Final[dict[int | str, dict[str, object]]] = {404: {"model": ErrorDetail}}
WAV_MEDIA_TYPE: Final[str] = "audio/wav"
WAV_CONTENT: Final[dict[str, dict[str, object]]] = {WAV_MEDIA_TYPE: {}}
