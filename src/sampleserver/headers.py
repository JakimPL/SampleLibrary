from __future__ import annotations

from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sampleserver.policy import ServingPolicy

EVERY_RESPONSE_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
# The application's pages load everything from this server. regl compiles its drawing commands with
# `Function`, wavesurfer writes a <style> into a shadow root and plays from a blob URL, and the build
# inlines its smallest font files as data URLs, which are the sources beyond the server's own the
# built pages need.
PAGE_CONTENT_SECURITY_POLICY: Final[str] = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "img-src 'self' data:",
        "media-src 'self' blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)
STRICT_TRANSPORT_SECURITY: Final[str] = "max-age=31536000"
PAGE_MEDIA_TYPE: Final[str] = "text/html"


class SecurityHeaders:
    """Middleware stating, on every response, what a browser may do with it.

    Every response is read as the type it states, sends its own address to no other site, and is
    framed by no page. A page of the application itself also carries its content security policy,
    and a library served over the internet tells browsers to reach it over HTTPS alone, as the
    serving policy says. The API's own pages under ``api_prefix``, its docs among them, keep what
    they load.
    """

    def __init__(self, app: ASGIApp, *, policy: ServingPolicy, api_prefix: str) -> None:
        self._app = app
        self._policy = policy
        self._api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = str(scope["path"])
        is_application_page = path != self._api_prefix and not path.startswith(f"{self._api_prefix}/")

        async def send_stated(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(EVERY_RESPONSE_HEADERS)
                if self._policy.requires_secure_transport:
                    headers["Strict-Transport-Security"] = STRICT_TRANSPORT_SECURITY
                if is_application_page and headers.get("content-type", "").startswith(PAGE_MEDIA_TYPE):
                    headers["Content-Security-Policy"] = PAGE_CONTENT_SECURITY_POLICY
            await send(message)

        await self._app(scope, receive, send_stated)
