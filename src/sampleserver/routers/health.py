from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from samplecore.models.base import FROZEN
from sampleserver.dependencies import READ_CONNECTION

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """What a health check reads: that the server answers and its catalog does too."""

    model_config = FROZEN

    catalog_answers: bool


@router.get("/health")
def get_health(connection: Connection = READ_CONNECTION) -> Health:
    """Whether the catalog answers, at the cost of one trivial query, for a platform checking the server's health."""
    connection.execute(text("SELECT 1")).scalar_one()
    return Health(catalog_answers=True)
