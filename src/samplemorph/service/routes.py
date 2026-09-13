from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from samplecore.models.morph import HeardMorphPoint, MorphServiceStatus
from samplemorph.service.dependencies import get_renderer
from samplemorph.service.renderer import MorphRenderer
from samplemorph.service.settings import CACHE_CONTROL, WAV_MEDIA_TYPE

router = APIRouter(prefix="/morph", tags=["morph"])


@router.get("/audio", response_class=Response)
def get_morph_audio(
    point: Annotated[HeardMorphPoint, Query()],
    request: Request,
    renderer: MorphRenderer = Depends(get_renderer),
) -> Response:
    """The audio at one point between two samples, as a WAV stating the rate the pair is heard at.

    The response names its render with a validator built from the loaded model and the point, so
    a caller that already holds it is answered with a bare 304 and no synthesis.

    Raises:
        HTTPException: 404 when the store holds no object for one of the two samples.
    """
    etag = renderer.etag(point)
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)

    try:
        rendered = renderer.render(point)
    except FileNotFoundError as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error

    return Response(content=rendered, media_type=WAV_MEDIA_TYPE, headers=headers)


@router.get("/status")
def get_morph_status(renderer: MorphRenderer = Depends(get_renderer)) -> MorphServiceStatus:
    """What this process serves: the model, the route, the device, and the fingerprint renders are named by."""
    return renderer.status()
