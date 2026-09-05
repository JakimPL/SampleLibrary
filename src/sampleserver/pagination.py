from __future__ import annotations

from typing import Final, Generic, TypeVar

from pydantic import BaseModel

from samplecore.models.base import FROZEN

DEFAULT_PAGE_LIMIT: Final[int] = 50
MAX_PAGE_LIMIT: Final[int] = 500

ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """One page of a listing endpoint's results, alongside the total count behind it."""

    model_config = FROZEN

    items: tuple[ItemT, ...]
    total: int
    limit: int
    offset: int
