from __future__ import annotations

from typing import Final

from samplecore.ports import ANY_PORT
from samplelibrary.app.instance.record import InstanceRecord

LOOPBACK_HOST: Final[str] = "127.0.0.1"
FIRST_APPLICATION_PORT: Final[int] = 27440
APPLICATION_PORT_CHOICES: Final[int] = 10


def port_choices(requested: int | None, previous: InstanceRecord | None) -> tuple[int, ...]:
    """The ports the application tries in turn: the one a person asked for alone, else its own list.

    Its own list starts with the port the last run under the same config listened on, which keeps
    the browser's layout, theme and cache, all kept per address. A few fixed ports come next, below
    the range systems hand out on their own, and a port the system assigns closes the list, so a
    start always finds one.
    """
    if requested is not None:
        return (requested,)
    fixed = tuple(range(FIRST_APPLICATION_PORT, FIRST_APPLICATION_PORT + APPLICATION_PORT_CHOICES))
    remembered = () if previous is None else (previous.port,)
    return tuple(dict.fromkeys((*remembered, *fixed, ANY_PORT)))
