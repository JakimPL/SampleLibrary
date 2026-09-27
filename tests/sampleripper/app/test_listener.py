from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest

from samplecore.ports import ANY_PORT
from sampleripper.app.instance.processes import ProcessIdentity
from sampleripper.app.instance.record import InstanceRecord
from sampleripper.app.listener import (
    APPLICATION_PORT_CHOICES,
    CLOSED_TO_THE_NETWORK,
    FIRST_APPLICATION_PORT,
    home_network_reach,
    port_choices,
    starting_policy,
)
from sampleserver.addresses import is_home_address, parsed_address
from tests.sampleserver.conftest import SITE_VISITORS_TABLE

FIXED_PORTS = tuple(range(FIRST_APPLICATION_PORT, FIRST_APPLICATION_PORT + APPLICATION_PORT_CHOICES))


def _record(port: int) -> InstanceRecord:
    return InstanceRecord(host="127.0.0.1", port=port, process=ProcessIdentity(pid=1, started_at=0.0))


def test_a_port_a_person_asks_for_is_the_only_choice() -> None:
    assert port_choices(8123, _record(30000)) == (8123,)


def test_a_first_start_tries_the_fixed_ports_then_any() -> None:
    assert port_choices(None, None) == (*FIXED_PORTS, ANY_PORT)


def test_a_later_start_tries_the_port_it_listened_on_last_first() -> None:
    assert port_choices(None, _record(30000)) == (30000, *FIXED_PORTS, ANY_PORT)


def test_a_remembered_port_among_the_fixed_ones_is_tried_once() -> None:
    remembered = FIXED_PORTS[3]

    assert port_choices(None, _record(remembered)) == (
        remembered,
        *(port for port in FIXED_PORTS if port != remembered),
        ANY_PORT,
    )


def _config(path: Path, server_tables: str) -> Path:
    path.write_text(
        f'[library]\nlibrary_root = "{(path.parent / "library").as_posix()}"\n{server_tables}', encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(
    ("server_tables", "opens_to_the_network"),
    [
        ("", False),
        ('[server]\nexposure = "local"\n', False),
        ('[server]\nexposure = "network"\n', True),
        (f'[server]\nexposure = "public"\n{SITE_VISITORS_TABLE}', False),
    ],
    ids=["unset", "this computer", "the home network", "anyone"],
)
def test_the_application_starts_open_to_the_network_its_config_opens_it_to(
    tmp_path: Path, server_tables: str, opens_to_the_network: bool
) -> None:
    policy = starting_policy(_config(tmp_path / "config.toml", server_tables))

    assert policy.listens_beyond_this_computer is opens_to_the_network
    assert policy.bind_host == ("0.0.0.0" if opens_to_the_network else "127.0.0.1")


def test_an_application_with_no_readable_config_starts_on_this_computer_alone(tmp_path: Path) -> None:
    unreadable = tmp_path / "config.toml"
    unreadable.write_text("[library\n", encoding="utf-8")

    assert not starting_policy(tmp_path / "absent.toml").listens_beyond_this_computer
    assert not starting_policy(unreadable).listens_beyond_this_computer


def test_an_application_open_to_the_network_names_a_home_address_or_none(tmp_path: Path) -> None:
    policy = starting_policy(_config(tmp_path / "config.toml", '[server]\nexposure = "network"\n'))

    reach = home_network_reach(policy, port=FIXED_PORTS[0])

    assert reach.open
    if reach.address is not None:
        parts = urlsplit(reach.address)
        address = parsed_address(parts.hostname)
        assert address is not None and is_home_address(address)
        assert parts.port == FIXED_PORTS[0]


def test_an_application_on_this_computer_alone_names_no_home_address(tmp_path: Path) -> None:
    policy = starting_policy(_config(tmp_path / "config.toml", ""))

    assert home_network_reach(policy, port=FIXED_PORTS[0]) == CLOSED_TO_THE_NETWORK
