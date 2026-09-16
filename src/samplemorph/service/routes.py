from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from samplecore.models.morph import HeardMorphPoint, MorphServiceStatus
from samplecore.storage.sample_audio import SampleUnavailableError
from samplemorph.service.dependencies import get_renderer
from samplemorph.service.renderer import MorphRenderer, RenderBoundsError
from samplemorph.service.settings import CACHE_CONTROL, WAV_MEDIA_TYPE

ANY_ENTITY_TAG: Final[str] = "*"
WEAK_TAG_PREFIX: Final[str] = "W/"

router = APIRouter(prefix="/morph", tags=["morph"])


@router.get("/audio", response_class=Response)
def get_morph_audio(
    point: Annotated[HeardMorphPoint, Query()],
    request: Request,
    renderer: MorphRenderer = Depends(get_renderer),
) -> Response:
    """The audio at one point between two samples, as a WAV stating the rate the pair is heard at.

    The response names its render with a validator built from the loaded route and the point, and
    asks every cache to check it before reuse, so a caller that holds the render is answered with
    a bare 304 and no synthesis, and a caller holding a render of another route is sent the new one.

    Raises:
        HTTPException: 404 when the store holds no object for an end, or an end's file is gone, holds
            another sample or lies outside every sample directory served; 422 when the point would
            render past the process's limits.
    """
    etag = renderer.etag(point)
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)

    try:
        renderer.check_bounds(point)
        rendered = renderer.render(point)
    except (FileNotFoundError, SampleUnavailableError) as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    except RenderBoundsError as error:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return Response(content=rendered, media_type=WAV_MEDIA_TYPE, headers=headers)


@router.get("/status")
def get_morph_status(renderer: MorphRenderer = Depends(get_renderer)) -> MorphServiceStatus:
    """What this process serves: the route, by kind and name, the device, and the fingerprint renders are named by."""
    return renderer.status()


def _matches(condition: str | None, etag: str) -> bool:
    """Whether an `If-None-Match` list names this validator, weakly or strongly, or names every one."""
    if condition is None:
        return False
    tags = (candidate.strip() for candidate in condition.split(","))
    return any(tag == ANY_ENTITY_TAG or tag.removeprefix(WEAK_TAG_PREFIX) == etag for tag in tags)
