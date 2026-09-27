from __future__ import annotations

import socket
from typing import Final

MINIMUM_PORT: Final[int] = 1
MAXIMUM_PORT: Final[int] = 65_535
ANY_PORT: Final[int] = 0


class PortUnavailableError(Exception):
    """Raised when none of the ports a process may listen on can be bound."""


def port_is_free(host: str, port: int) -> bool:
    """Whether a server could bind ``port`` on ``host`` at this moment.

    The answer holds until another program binds the port, so a process handing the port to a
    server it starts next takes the rare clash that follows as that server's own start failure.
    """
    with socket.socket(_family(host), socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
        return True


def free_port(host: str, *, preferred: tuple[int, ...]) -> int:
    """The first of the preferred ports free on ``host``, or one the system assigns when every one is taken.

    Raises:
        PortUnavailableError: the system assigns no port on ``host``, which is then no address of this machine.
    """
    for port in preferred:
        if port_is_free(host, port):
            return port
    with socket.socket(_family(host), socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, ANY_PORT))
        except OSError as error:
            raise PortUnavailableError(f"No port on {host} can be bound: {error}") from error
        assigned: int = probe.getsockname()[1]
        return assigned


def listen_on_first_free(host: str, ports: tuple[int, ...]) -> socket.socket:
    """A socket listening on the first of ``ports`` this process can bind on ``host``.

    `ANY_PORT` among them stands for a port the system assigns. The socket is made the way the
    standard library makes a server's: on POSIX systems it binds a port its previous listener left
    waiting on closed connections, which keeps a restarted server on its old port, and on Windows it
    takes the port as it is.

    Raises:
        PortUnavailableError: none of the ports can be bound.
    """
    for port in ports:
        try:
            return socket.create_server((host, port), family=_family(host))
        except OSError:
            continue
    raise PortUnavailableError(f"None of the ports {', '.join(map(str, ports))} on {host} can be bound.")


def _family(host: str) -> socket.AddressFamily:
    """The address family of ``host``: IPv6 for an address with colons, IPv4 for any other address or name."""
    return socket.AF_INET6 if ":" in host else socket.AF_INET
