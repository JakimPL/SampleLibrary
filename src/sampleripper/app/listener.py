from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.config import DEFAULT_SERVER_CONFIG, ConfigurationError, load_config
from samplecore.models.base import FROZEN
from samplecore.ports import ANY_PORT
from sampleripper.app.instance.record import InstanceRecord
from sampleserver.addresses import home_network_address
from sampleserver.policy import ServingPolicy

LOOPBACK_HOST: Final[str] = "127.0.0.1"
FIRST_APPLICATION_PORT: Final[int] = 27440
APPLICATION_PORT_CHOICES: Final[int] = 10


class HomeNetworkReach(BaseModel):
    """Whether this run of the application answers the devices on the home network, and the address they open it at.

    It holds from the start of the run to its end, whatever the config says meanwhile. ``address``
    is None while this computer is on no home network.
    """

    model_config = FROZEN

    open: bool
    address: str | None


CLOSED_TO_THE_NETWORK: Final[HomeNetworkReach] = HomeNetworkReach(open=False, address=None)


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


def starting_policy(config_path: Path) -> ServingPolicy:
    """Whom the application answers from this start on, as its config says: this computer, or the home network too.

    A config the application cannot read yet, or one serving the library to anyone, which the
    application never opens, starts it on this computer alone. A change made later on the setup page
    takes effect at the next start.
    """
    local = ServingPolicy.of(DEFAULT_SERVER_CONFIG)
    try:
        policy = ServingPolicy.of(load_config(config_path).server)
    except ConfigurationError:
        return local
    return policy if policy.permits_desktop_app else local


def home_network_reach(policy: ServingPolicy, *, port: int) -> HomeNetworkReach:
    """Whether a run listening on ``port`` under ``policy`` answers the home network, and at which address."""
    if not policy.listens_beyond_this_computer:
        return CLOSED_TO_THE_NETWORK
    address = home_network_address()
    return HomeNetworkReach(open=True, address=f"http://{address}:{port}/" if address is not None else None)
