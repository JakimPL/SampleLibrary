from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Final

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import Match, Mount
from starlette.staticfiles import StaticFiles
from starlette.status import HTTP_404_NOT_FOUND
from starlette.types import Scope

FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_FRONTEND_DIRECTORY"
INDEX_DOCUMENT: Final[str] = "index.html"


class SinglePageApplication(StaticFiles):
    """The built frontend: each of its files as it is, and its index for every page path outside the API.

    The application routes in the browser, so a reload on `/samples/{hash}` asks the server for a path
    no file carries; answering it with the index lets the application take that route over again.
    A path naming a file, one with an extension, and a path under the API prefix answer a miss with a
    plain 404, so a stale asset reference fails as itself.
    """

    def __init__(self, directory: Path, *, api_prefix: str) -> None:
        super().__init__(directory=directory, html=True)
        self._api_segment = api_prefix.strip("/")

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != HTTP_404_NOT_FOUND or not self._is_page_path(path):
                raise
            return await super().get_response(INDEX_DOCUMENT, scope)

    def _is_page_path(self, path: str) -> bool:
        under_api = path == self._api_segment or path.startswith(f"{self._api_segment}/")
        return not under_api and not PurePosixPath(path).suffix


class FrontendMount(Mount):
    """The built frontend mounted at the root, taking every path outside the API's own segment.

    A request under the API prefix that no API route takes is then the API's own to answer: a
    wrong method gets its 405 with the methods allowed, a trailing slash its redirect, and an
    unknown path its JSON 404, the same whether or not a frontend is served beside it.
    """

    def __init__(self, directory: Path, *, api_prefix: str) -> None:
        super().__init__("/", app=SinglePageApplication(directory, api_prefix=api_prefix), name="frontend")
        self._api_prefix = api_prefix.rstrip("/")

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        path: str = scope.get("path", "")
        if path == self._api_prefix or path.startswith(f"{self._api_prefix}/"):
            return Match.NONE, {}
        return super().matches(scope)


def built_frontend(directory: Path) -> Path:
    """The directory, resolved, once it is known to hold a built frontend.

    Raises:
        ValueError: the directory holds no index document.
    """
    resolved = directory.resolve()
    if not (resolved / INDEX_DOCUMENT).is_file():
        raise ValueError(f"{resolved} holds no {INDEX_DOCUMENT}, so it is no built frontend")
    return resolved


def frontend_directory_from_environment() -> Path | None:
    """The built frontend `samplelibrary serve --frontend` hands every worker, if it named one.

    Raises:
        ValueError: the variable names a directory holding no built frontend.
    """
    raw_directory = os.environ.get(FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE)
    if not raw_directory:
        return None
    try:
        return built_frontend(Path(raw_directory))
    except ValueError as error:
        raise ValueError(f"{FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE}: {error}") from error
