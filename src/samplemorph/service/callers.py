from __future__ import annotations

from typing import Final

from fastapi import status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from samplecore.host_header import requested_host

LOOPBACK_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
PAGE_REFUSED_DETAIL: Final[str] = "The morph renderer answers programs calling it by its own address, and no web page."
HOST_HEADER: Final[str] = "host"
BROWSER_HEADERS: Final[tuple[str, ...]] = ("origin", "sec-fetch-site")


class ProgramsCallingItsAddressOnly:
    """Middleware answering the programs that call the renderer by the address it listens on, and no web page.

    The catalog API and a sampler plugin call the renderer by its address and send none of
    `BROWSER_HEADERS`: a browser sends `Sec-Fetch-Site` with every request and `Origin` with a
    page's requests elsewhere, so a page on another site that asks the renderer for anything is
    turned away. So is a page that points its own name at
    the renderer's address, whose `Host` header, read as sent, names that site rather than the
    renderer (`samplecore.host_header.requested_host`).
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
        headers = connection.headers
        return (
            not any(header in headers for header in BROWSER_HEADERS)
            and requested_host(headers.getlist(HOST_HEADER)) in self._names
        )
