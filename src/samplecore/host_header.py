from __future__ import annotations

import re
from collections.abc import Sequence
from ipaddress import IPv6Address, ip_address
from typing import Final

# A name or an address as a `Host` header carries it, then an optional port; an IPv6 address sits in
# brackets. Anything a URL's host cannot hold, such as a user, a path or a space, fails the match.
HOST_VALUE: Final[re.Pattern[str]] = re.compile(
    r"(?:\[(?P<bracketed>[^\]]+)\]|(?P<name>[^\s:/?#@\[\]\\]+))(?::\d{1,5})?"
)


def requested_host(values: Sequence[str]) -> str | None:
    """The host a request names in its one `Host` header, in lower case and without its port.

    A server answering its own computer or home network decides from this value whom a request is
    for, so it reads the header as sent: the name a page's address holds, whatever characters it
    uses, stays that name and never matches this computer's.

    Returns:
        None for a request with no `Host` header, with more than one, or with one no URL could hold.
    """
    if len(values) != 1:
        return None
    match = HOST_VALUE.fullmatch(values[0])
    if match is None:
        return None
    bracketed = match.group("bracketed")
    if bracketed is None:
        return match.group("name").lower()
    try:
        address = ip_address(bracketed)
    except ValueError:
        return None
    return str(address) if isinstance(address, IPv6Address) else None
