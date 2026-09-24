from __future__ import annotations

from ipaddress import ip_address
from typing import Final
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from samplelibrary.app.launcher import Launcher

LOCAL_HOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})


def require_local_person(request: Request) -> None:
    """Admit a setup request only from a browser on this machine, addressing the application by a local name.

    The setup routes list folders and write the config file, so they answer the person sitting at
    the machine: the connection comes from the loopback address, it addresses the application by a
    local name, and a page that sent it was loaded from a local name, which a web page from elsewhere
    cannot claim.

    Raises:
        HTTPException: 403 for a request from another machine, one addressing the application by
            another name, or one a page from elsewhere sent.
    """
    client = request.client
    origin = request.headers.get("origin")
    if (
        client is None
        or not _is_loopback(client.host)
        or request.url.hostname not in LOCAL_HOST_NAMES
        or (origin is not None and urlsplit(origin).hostname not in LOCAL_HOST_NAMES)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Setup is only available on this computer.")


def launcher_of(request: Request) -> Launcher:
    launcher: Launcher = request.app.state.launcher
    return launcher


def _is_loopback(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
