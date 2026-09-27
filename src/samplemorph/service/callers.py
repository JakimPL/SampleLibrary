from __future__ import annotations

from typing import Final

from fastapi import status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
PAGE_REFUSED_DETAIL: Final[str] = "The morph renderer answers programs calling it by its own address, and no web page."
ORIGIN_HEADER: Final[str] = "origin"


class ProgramsCallingItsAddressOnly:
    """Middleware answering the programs that call the renderer by the address it listens on, and no web page.

    The catalog API and a sampler plugin call the renderer by its address and send no ``Origin``;
    a browser sends one with every request a page makes elsewhere, so a page on another site that
    posts to the renderer is turned away, and so is one that points its own name at the renderer's
    address, which names that site rather than the renderer.
    """

    def __init__(self, app: ASGIApp, *, host: str) -> None:
        self._app = app
        self._names = LOOPBACK_NAMES | {host.lower()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._admitted(HTTPConnection(scope)):
            response = JSONResponse({"detail": PAGE_REFUSED_DETAIL}, status_code=status.HTTP_403_FORBIDDEN)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _admitted(self, connection: HTTPConnection) -> bool:
        hostname = connection.url.hostname
        return ORIGIN_HEADER not in connection.headers and hostname is not None and hostname.lower() in self._names
