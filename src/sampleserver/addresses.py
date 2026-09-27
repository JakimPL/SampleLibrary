from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address


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
