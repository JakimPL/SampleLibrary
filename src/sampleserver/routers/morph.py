from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.morph import HeardMorphPoint, MorphPoint, MorphServiceStatus
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.playback_rates import resolved_playback_rates
from sampleserver.dependencies import get_connection, get_inference_client
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


def get_heard_point(
    point: Annotated[MorphPoint, Query()], connection: Connection = Depends(get_connection)
) -> HeardMorphPoint:
    """The point with the rate each end is heard at, by the one rule every reader of the catalog applies.

    A sample the catalog holds no rate for is heard as stored, at the nominal rate its file
    states, which is the reading every player of such a sample gives it.
    """
    rates = resolved_playback_rates(connection, [point.first, point.second])
    return HeardMorphPoint(
        first=point.first,
        second=point.second,
        weight=point.weight,
        first_rate_hz=_heard_rate(rates[point.first]),
        second_rate_hz=_heard_rate(rates[point.second]),
    )


def _heard_rate(rate: Rate | None) -> Rate:
    return NOMINAL_WAV_RATE if rate is None else rate


@router.get("/audio", response_class=Response)
async def get_morph_audio(
    request: Request,
    point: HeardMorphPoint = Depends(get_heard_point),
    client: httpx.AsyncClient = Depends(get_inference_client),
) -> Response:
    """The audio at one point between two samples, rendered by the inference process and relayed as it came.

    The catalog's rates for both ends travel with the point, so the process renders the pair in
    the one frame it is heard in and the file states that rate. The render's validator and its
    caching headers pass through untouched, and so does a caller's conditional request, so a
    browser that holds the render is answered with a 304 by the process that made it.

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
