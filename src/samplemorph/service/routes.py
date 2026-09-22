from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile

from samplecore.models.morph import HeardMorphPoint, MorphPair, MorphServiceStatus
from samplecore.storage.sample_audio import SampleUnavailableError
from samplemorph.service.dependencies import get_renderer
from samplemorph.service.renderer import MorphRenderer, RenderBoundsError
from samplemorph.service.settings import CACHE_CONTROL, RESPONSE_MEDIA_TYPE, WAV_MEDIA_TYPE
from samplemorph.service.uploads import UploadTooLargeError, UploadUnreadableError

ANY_ENTITY_TAG: Final[str] = "*"
WEAK_TAG_PREFIX: Final[str] = "W/"
CONDITIONAL_HEADER: Final[str] = "if-none-match"

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
    if _matches(request.headers.get(CONDITIONAL_HEADER), etag):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)

    try:
        renderer.check_bounds(point)
        rendered = renderer.render(point)
    except (FileNotFoundError, SampleUnavailableError) as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    except RenderBoundsError as error:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return Response(content=rendered, media_type=WAV_MEDIA_TYPE, headers=headers)


@router.get("/response", response_class=Response)
def get_morph_response(
    pair: Annotated[MorphPair, Query()],
    request: Request,
    renderer: MorphRenderer = Depends(get_renderer),
) -> Response:
    """The filter between two samples, which a caller applies at every weight between them.

    One answer serves a whole path, so a caller holding it moves its own weight without asking
    again. The response names itself with a validator built from the route filters are read under and
    the pair, so a caller that already holds the filter is answered with a bare 304.

    Raises:
        HTTPException: 404 when the store holds no object for an end, or an end's file is gone, holds
            another sample or lies outside every sample directory served; 422 when the pair reaches
            past the process's limits.
    """
    etag = renderer.pair_etag(pair)
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _matches(request.headers.get(CONDITIONAL_HEADER), etag):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)

    try:
        renderer.check_bounds(pair)
        written = renderer.response(pair)
    except (FileNotFoundError, SampleUnavailableError) as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    except RenderBoundsError as error:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return Response(content=written, media_type=RESPONSE_MEDIA_TYPE, headers=headers)


@router.post("/response", response_class=Response)
def post_morph_response(
    first: UploadFile, second: UploadFile, renderer: MorphRenderer = Depends(get_renderer)
) -> Response:
    """The filter between two sounds the caller sends, which it applies at every weight between them.

    A caller holding its own audio, a sampler among them, sends both sounds as audio files and reads
    the filter back once; the sounds may come from anywhere, since the process reads only what was
    sent. The pair is heard at the higher of the two rates the files state.

    Raises:
        HTTPException: 413 when an upload runs past the bytes one request may carry; 422 when an
            upload holds no audio this process decodes, or the pair reaches past the process's limits.
    """
    try:
        sounds = (renderer.uploaded_sound(first.file), renderer.uploaded_sound(second.file))
        renderer.check_upload_bounds(*sounds)
        written = renderer.uploaded_response(*sounds)
    except UploadTooLargeError as error:
        raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail=str(error)) from error
    except (UploadUnreadableError, RenderBoundsError) as error:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return Response(content=written, media_type=RESPONSE_MEDIA_TYPE)


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
