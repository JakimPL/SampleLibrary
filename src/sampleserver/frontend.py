from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Final

from starlette.exceptions import HTTPException
from starlette.responses import Response
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


def frontend_directory_from_environment() -> Path | None:
    """The built frontend `samplelibrary serve --frontend` hands every worker, if it named one."""
    raw_directory = os.environ.get(FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE)
    return Path(raw_directory) if raw_directory else None
