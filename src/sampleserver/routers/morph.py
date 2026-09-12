from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.morph import MorphPoint, MorphServiceStatus
from sampleserver.dependencies import get_inference_client
from sampleserver.inference_client import unavailable_detail

router = APIRouter(prefix="/morph", tags=["morph"])

AUDIO_PATH: Final[str] = "/morph/audio"
STATUS_PATH: Final[str] = "/morph/status"
RELAYED_HEADERS: Final[frozenset[str]] = frozenset({"etag", "cache-control"})
CONDITIONAL_HEADER: Final[str] = "if-none-match"
WAV_MEDIA_TYPE: Final[str] = "audio/wav"


class MorphAvailability(BaseModel):
    """Whether morphs can be rendered right now, and by which model when they can."""

    model_config = FROZEN

    available: bool
    service: MorphServiceStatus | None


@router.get("/audio", response_class=Response)
async def get_morph_audio(
    point: Annotated[MorphPoint, Query()],
    request: Request,
    client: httpx.AsyncClient = Depends(get_inference_client),
) -> Response:
    """The audio at one point between two samples, rendered by the inference process and relayed as it came.

    The render's validator and its caching headers pass through untouched, and so does a caller's
    conditional request, so a browser that holds the render is answered with a 304 by the process
    that made it.

    Raises:
        HTTPException: 503 when no inference process answers; the process's own 404 for a sample
            it has no object for, and 422 for a weight off the grid, are relayed with their detail.
    """
    headers = {CONDITIONAL_HEADER: request.headers[CONDITIONAL_HEADER]} if CONDITIONAL_HEADER in request.headers else {}
    try:
        upstream = await client.get(AUDIO_PATH, params=point.model_dump(), headers=headers)
    except httpx.TransportError as error:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=unavailable_detail(str(client.base_url))
        ) from error

    relayed = {name: value for name, value in upstream.headers.items() if name.lower() in RELAYED_HEADERS}
    if upstream.status_code == HTTPStatus.NOT_MODIFIED:
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=relayed)
    if upstream.status_code != HTTPStatus.OK:
        raise HTTPException(status_code=upstream.status_code, detail=upstream.json()["detail"])

    return Response(content=upstream.content, media_type=WAV_MEDIA_TYPE, headers=relayed)


@router.get("/status")
async def get_morph_status(client: httpx.AsyncClient = Depends(get_inference_client)) -> MorphAvailability:
    """Whether the inference process answers, and what it serves when it does."""
    try:
        upstream = await client.get(STATUS_PATH)
    except httpx.TransportError:
        return MorphAvailability(available=False, service=None)

    if upstream.status_code != HTTPStatus.OK:
        return MorphAvailability(available=False, service=None)

    return MorphAvailability(available=True, service=MorphServiceStatus.model_validate(upstream.json()))
