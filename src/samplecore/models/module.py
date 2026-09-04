from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Count, Index, ModuleHash
from samplecore.models.tracker import TrackerFormat


class Module(BaseModel):
    """A tracker module file's identity and the shape of the song it stores.

    ``hash`` content-addresses the exact file bytes; ``id`` is the library's own sequential handle
    for it, the pair mirroring how modsamplemaster.org identifies a module by both a hash and an
    id. ``filename`` is the module's own filename at ingestion time with no directory component --
    the local path it was ingested from is never recorded, only the name the file itself carried.
    """

    model_config = FROZEN

    hash: ModuleHash
    id: Index
    filename: str
    tracker: TrackerFormat
    title: str
    channel_count: Count
    pattern_count: Count
    instrument_count: Count
    sample_count: Count
    file_size: Count
    ingested_at: datetime

    @field_validator("filename")
    @classmethod
    def _no_path_separators(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError(f"filename {value!r} must not contain a path separator")

        return value
