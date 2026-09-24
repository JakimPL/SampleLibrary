from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from starlette.datastructures import URLPath
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from starlette.types import Receive, Scope, Send

from samplelibrary.app.launcher import Launcher
from samplelibrary.app.routes import setup
from sampleserver.app import API_PREFIX
from sampleserver.frontend import FrontendMount

SETUP_PREFIX: Final[str] = f"{API_PREFIX}/setup"
CLOSED_LIBRARY_DETAIL: Final[str] = "The library isn't open yet. Check the setup page."


class CatalogRoute(BaseRoute):
    """Every API path outside the setup routes, answered by the catalog API while the library is open.

    The catalog API is built again whenever the library opens under new folders, so this route asks
    the launcher for it on each request, and answers 503 while there is none.
    """

    def __init__(self, launcher: Launcher) -> None:
        self._launcher = launcher

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        path: str = scope.get("path", "")
        if scope["type"] == "http" and (path == API_PREFIX or path.startswith(f"{API_PREFIX}/")):
            return Match.FULL, {}
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: object) -> URLPath:
        """The catalog API names its own routes, so this route names none.

        Raises:
            NoMatchFound: always.
        """
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        catalog = self._launcher.catalog
        if catalog is None:
            await JSONResponse({"detail": CLOSED_LIBRARY_DETAIL}, status_code=HTTP_503_SERVICE_UNAVAILABLE)(
                scope, receive, send
            )
            return
        await catalog(scope, receive, send)


def create_application(launcher: Launcher, *, frontend_directory: Path | None, on_ready: Callable[[], None]) -> FastAPI:
    """The one app the application serves: the setup routes, the catalog API behind them, and the frontend.

    Its lifespan opens the library as the server starts and closes it, with everything it runs, as
    the server stops. ``on_ready`` runs once the server is about to answer, which is when the
    application opens a browser on it.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:  # pylint: disable=unused-argument
        launcher.start()
        on_ready()
        try:
            yield
        finally:
            await launcher.stop()

    application = FastAPI(
        openapi_url=f"{SETUP_PREFIX}/openapi.json",
        docs_url=None,
        redoc_url=None,
        title="SampleLibrary setup",
        lifespan=lifespan,
    )
    application.state.launcher = launcher
    application.include_router(setup.router, prefix=SETUP_PREFIX)
    application.router.routes.append(CatalogRoute(launcher))
    if frontend_directory is not None:
        application.router.routes.append(FrontendMount(frontend_directory, api_prefix=API_PREFIX))
    return application
