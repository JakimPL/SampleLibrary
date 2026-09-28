from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection, text

from samplecore.models.base import FROZEN
from samplecore.storage.audio_store import store_holds_audio
from sampleserver.dependencies import READ_CONNECTION, get_library_root

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """What a health check reads: that the server answers, its catalog does too, and whether its audio is in place.

    ``audio_present`` is False while the store holds nothing, as a site's volume does before the
    publication's objects are uploaded; the server answers all the same.
    """

    model_config = FROZEN

    catalog_answers: bool
    audio_present: bool


@router.get("/health")
def get_health(connection: Connection = READ_CONNECTION, library_root: Path = Depends(get_library_root)) -> Health:
    """Whether the catalog answers, at the cost of one trivial query, and whether the audio store holds anything."""
    connection.execute(text("SELECT 1")).scalar_one()
    return Health(catalog_answers=True, audio_present=store_holds_audio(library_root))
