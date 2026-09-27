from __future__ import annotations

import socket
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network
from typing import Final

from samplecore.config import Exposure, ServerConfig, VisitorLimits
from sampleserver.addresses import is_loopback, parsed_address

LOCAL_HOST_NAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
LOOPBACK_BIND_HOST: Final[str] = "127.0.0.1"
LOCAL_NETWORK_SUFFIX: Final[str] = ".local"
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


@dataclass(frozen=True)
class ServingPolicy:
    """Everything a served library does differently for the people it is served to, derived from its exposure alone.

    The configured exposure is the one thing that decides: every route, middleware and command that
    behaves differently on this computer, on a home network or on the internet reads one of these
    properties, and nothing a request carries changes which exposure applies. A request can only be
    turned away by `admits`, never let further than the configuration allows.
    """

    _exposure: Exposure
    _visitors: VisitorLimits | None

    @classmethod
    def of(cls, server: ServerConfig) -> ServingPolicy:
        return cls(_exposure=server.exposure, _visitors=server.visitors)

    @property
    def is_public(self) -> bool:
        """Whether anyone on the internet may reach the library, which a site alone serves."""
        return self._exposure is Exposure.PUBLIC

    @property
    def shows_paths(self) -> bool:
        """Whether a sample file is named by the full path of its folder on this computer, or by the folder's name."""
        return not self.is_public

    @property
    def reports_file_availability(self) -> bool:
        """Whether the server says if a sample's file is still there, which it checks on its own disk."""
        return not self.is_public

    @property
    def names_internals(self) -> bool:
        """Whether a refusal names the file, the address or the process behind it, for the person running it."""
        return not self.is_public

    @property
    def shows_curation(self) -> bool:
        """Whether the labels, ratings and favorites a person decided are served at all."""
        return not self.is_public

    @property
    def shows_reviewers(self) -> bool:
        """Whether a relation's review names who reviewed it."""
        return not self.is_public

    @property
    def serves_uncataloged_audio(self) -> bool:
        """Whether a stored object is served by its hash alone, or only for a sample the catalog holds."""
        return not self.is_public

    @property
    def serves_docs(self) -> bool:
        """Whether the API describes itself on pages of its own."""
        return not self.is_public

    @property
    def requires_secure_transport(self) -> bool:
        """Whether browsers are told to reach the library over HTTPS alone, as a site behind a platform's edge is."""
        return self.is_public

    @property
    def permits_desktop_app(self) -> bool:
        """Whether the SampleLibrary app, which edits labels and writes its config, may serve the library."""
        return not self.is_public

    @property
    def permits_serve(self) -> bool:
        """Whether `samplelibrary serve` may serve the library; a site starts through `samplelibrary site` alone."""
        return not self.is_public

    @property
    def permits_site(self) -> bool:
        """Whether `samplelibrary site` may serve the library, which it does to anyone."""
        return self.is_public

    @property
    def listens_beyond_this_computer(self) -> bool:
        """Whether the server listens on every address rather than the loopback address alone."""
        return self._exposure is not Exposure.LOCAL

    @property
    def visitor_limits(self) -> VisitorLimits | None:
        """How much each visitor may ask, where anyone may visit; a library at home limits no one."""
        return self._visitors if self.is_public else None

    def refusal(self, internal: str, *, plain: str) -> str:
        """What a refusal says: its ``internal`` detail where the policy names internals, the ``plain`` words otherwise."""
        return internal if self.names_internals else plain

    def binds(self, host: str) -> bool:
        """Whether a server may listen on ``host``: any address once it listens beyond this computer, loopback otherwise."""
        return self.listens_beyond_this_computer or host in LOCAL_HOST_NAMES or is_loopback(host)

    def admits(self, peer: str | None, host: str | None) -> bool:
        """Whether a request from ``peer``, naming the server as ``host``, is one this exposure answers.

        On this computer alone, the request comes from the loopback address and names the server by
        a local name, so a page on another site that points its own name at the loopback address
        still names that site and is turned away. On a home network, a device on one of
        `HOME_NETWORKS` is answered too, and so is a program on this computer passing a device's
        request on, such as a development server, each naming the server by an address or by this
        computer's own name. A site answers anyone.
        """
        if self.is_public:
            return True
        if peer is None or host is None:
            return False
        address = parsed_address(peer)
        if address is None:
            return False
        if address.is_loopback and host.lower() in LOCAL_HOST_NAMES:
            return True
        if self._exposure is Exposure.LOCAL:
            return False
        from_home = address.is_loopback or any(address in network for network in HOME_NETWORKS)
        return from_home and _names_this_computer(host)


def _names_this_computer(host: str) -> bool:
    """Whether ``host`` names this computer as a device on the home network reaches it: by an address, or by its name."""
    if parsed_address(host) is not None:
        return True
    name = socket.gethostname().lower()
    return host.lower() in {name, f"{name}{LOCAL_NETWORK_SUFFIX}"}
