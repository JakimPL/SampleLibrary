from __future__ import annotations

import pytest

from samplecore.host_header import requested_host


@pytest.mark.parametrize(
    ("values", "host"),
    [
        (["localhost"], "localhost"),
        (["LocalHost:27440"], "localhost"),
        (["127.0.0.1:27440"], "127.0.0.1"),
        (["[::1]:27440"], "::1"),
        (["[::ffff:127.0.0.1]"], "::ffff:127.0.0.1"),
        (["a_b.attacker.example:27440"], "a_b.attacker.example"),
        (["site.example"], "site.example"),
    ],
)
def test_a_host_header_names_its_host_as_sent(values: list[str], host: str) -> None:
    assert requested_host(values) == host


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["localhost", "localhost"],
        [""],
        ["attacker.example@localhost"],
        ["localhost/path"],
        ["local host"],
        ["localhost:port"],
        ["localhost:123456"],
        ["[not-an-address]"],
        ["[127.0.0.1]"],
        ["::1"],
    ],
    ids=repr,
)
def test_a_host_header_no_url_could_hold_names_no_host(values: list[str]) -> None:
    assert requested_host(values) is None
