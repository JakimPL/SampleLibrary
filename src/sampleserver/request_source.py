from __future__ import annotations

from typing import Final

from starlette.requests import HTTPConnection

from samplecore.host_header import requested_host

HOST_HEADER: Final[str] = "host"
FETCH_SITE_HEADER: Final[str] = "sec-fetch-site"
FETCH_MODE_HEADER: Final[str] = "sec-fetch-mode"
CROSS_SITE: Final[str] = "cross-site"
NAVIGATION: Final[str] = "navigate"


def host_of(connection: HTTPConnection) -> str | None:
    """The host a request names, read from its `Host` header as sent (`samplecore.host_header.requested_host`)."""
    return requested_host(connection.headers.getlist(HOST_HEADER))


def sent_by_another_site(connection: HTTPConnection) -> bool:
    """Whether a page on another site sent the request, other than as a link a person followed.

    A browser names where the page asking comes from in `Sec-Fetch-Site` with every request, the
    ones sending no `Origin` included, such as an image's or an audio element's. Following a link is
    a navigation, which hands the other site nothing back.
    """
    headers = connection.headers
    return headers.get(FETCH_SITE_HEADER) == CROSS_SITE and headers.get(FETCH_MODE_HEADER) != NAVIGATION
