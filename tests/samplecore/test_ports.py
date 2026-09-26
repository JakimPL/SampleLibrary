from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Final

import pytest

from samplecore.ports import ANY_PORT, PortUnavailableError, free_port, listen_on_first_free, port_is_free

LOOPBACK: Final[str] = "127.0.0.1"


@pytest.fixture
def held_port() -> Iterator[int]:
    with socket.create_server((LOOPBACK, ANY_PORT)) as holder:
        port: int = holder.getsockname()[1]
        yield port


@pytest.fixture
def released_port() -> int:
    with socket.create_server((LOOPBACK, ANY_PORT)) as holder:
        port: int = holder.getsockname()[1]
    return port


def test_a_port_another_socket_listens_on_is_taken(held_port: int) -> None:
    assert not port_is_free(LOOPBACK, held_port)


def test_a_free_preferred_port_is_chosen(released_port: int) -> None:
    assert free_port(LOOPBACK, preferred=(released_port,)) == released_port


def test_a_taken_preferred_port_gives_way_to_one_the_system_assigns(held_port: int) -> None:
    chosen = free_port(LOOPBACK, preferred=(held_port,))

    assert chosen != held_port
    assert port_is_free(LOOPBACK, chosen)


def test_a_listener_takes_the_first_port_it_can_bind(held_port: int, released_port: int) -> None:
    with listen_on_first_free(LOOPBACK, (held_port, released_port)) as listener:
        assert listener.getsockname()[1] == released_port
        with socket.create_connection((LOOPBACK, released_port)):
            pass


def test_a_listener_falls_back_to_a_port_the_system_assigns(held_port: int) -> None:
    with listen_on_first_free(LOOPBACK, (held_port, ANY_PORT)) as listener:
        assert listener.getsockname()[1] not in (held_port, ANY_PORT)


def test_a_listener_with_every_port_taken_is_refused(held_port: int) -> None:
    with pytest.raises(PortUnavailableError):
        listen_on_first_free(LOOPBACK, (held_port,))
