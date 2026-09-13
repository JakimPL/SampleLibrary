from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.status import HTTP_404_NOT_FOUND
from starlette.types import Scope

FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_FRONTEND_DIRECTORY"
INDEX_DOCUMENT: Final[str] = "index.html"


class SinglePageApplication(StaticFiles):
    """The built frontend: each of its files as it is, and its index for every other path outside the API.

    The application routes in the browser, so a reload on `/samples/{hash}` asks the server for a path
    no file carries; answering it with the index lets the application take that route over again.
    A path under the API prefix stays the API's own, and a miss there is a plain 404.
    """

    def __init__(self, directory: Path, *, api_prefix: str) -> None:
        super().__init__(directory=directory, html=True)
        self._api_segment = api_prefix.strip("/")

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != HTTP_404_NOT_FOUND or self._is_api_path(path):
                raise
            return await super().get_response(INDEX_DOCUMENT, scope)

    def _is_api_path(self, path: str) -> bool:
        return path == self._api_segment or path.startswith(f"{self._api_segment}/")


def frontend_directory_from_environment() -> Path | None:
    """The built frontend `samplelibrary serve --frontend` hands every worker, if it named one."""
    raw_directory = os.environ.get(FRONTEND_DIRECTORY_ENVIRONMENT_VARIABLE)
    return Path(raw_directory) if raw_directory else None
