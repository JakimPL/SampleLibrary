from __future__ import annotations

from typing import Final

from fastapi import status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sampleserver.messages import NOT_ADMITTED
from sampleserver.policy import ServingPolicy

POLICY_VIOLATION_CLOSE_CODE: Final[int] = 1008


class AdmittedRequestsOnly:
    """Middleware answering exactly the requests the serving policy admits, on every path.

    Which requests those are follows from the configured exposure alone (`ServingPolicy.admits`):
    the address a request comes from and the name it gives the server can only turn it away.
    """

    def __init__(self, app: ASGIApp, *, policy: ServingPolicy) -> None:
        self._app = app
        self._policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and not self._admitted(HTTPConnection(scope)):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": POLICY_VIOLATION_CLOSE_CODE})
                return
            response = JSONResponse({"detail": NOT_ADMITTED}, status_code=status.HTTP_403_FORBIDDEN)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _admitted(self, connection: HTTPConnection) -> bool:
        client = connection.client
        return self._policy.admits(client.host if client is not None else None, connection.url.hostname)
