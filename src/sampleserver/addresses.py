from __future__ import annotations

import socket
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from typing import Final

LOOPBACK_NAME: Final[str] = "localhost"
# The networks a home network hands its devices addresses from, named one by one: the standard
# library's own notion of a private address also covers ranges no home network uses, such as the
# benchmarking range, which a device elsewhere can present itself from.
HOME_NETWORKS: Final[tuple[IPv4Network | IPv6Network, ...]] = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
    IPv4Network("169.254.0.0/16"),
    IPv6Network("fc00::/7"),
    IPv6Network("fe80::/10"),
)
# An address of the documentation range, which a datagram socket names as its peer to learn the
# address this computer reaches the network from; connecting such a socket sends nothing.
ROUTE_PROBE: Final[tuple[str, int]] = ("192.0.2.1", 9)


def parsed_address(value: str | None) -> IPv4Address | IPv6Address | None:
    """The address ``value`` names, an IPv4 address carried in IPv6 unwrapped to itself; ``None`` for anything else."""
    if value is None:
        return None
    try:
        address = ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_loopback(host: str) -> bool:
    """Whether ``host`` is an address of this computer's loopback interface."""
    address = parsed_address(host)
    return address is not None and address.is_loopback


def names_loopback(host: str) -> bool:
    """Whether ``host`` names this computer's loopback interface: ``localhost``, or a loopback address."""
    return host.lower() == LOOPBACK_NAME or is_loopback(host)


def is_home_address(address: IPv4Address | IPv6Address) -> bool:
    """Whether ``address`` is one a home network hands its devices."""
    return any(address in network for network in HOME_NETWORKS)


def home_network_address() -> str | None:
    """The address this computer reaches its home network from, for a device on it to open; ``None`` off one."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(ROUTE_PROBE)
        except OSError:
            return None
        own = str(probe.getsockname()[0])
    address = parsed_address(own)
    return own if address is not None and is_home_address(address) else None
