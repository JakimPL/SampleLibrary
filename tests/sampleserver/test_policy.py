from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Final

import pytest

from samplecore.config import Exposure, ServerConfig
from sampleserver.policy import HOME_CONCURRENT_MORPHS, ServingPolicy
from tests.sampleserver.conftest import SITE_VISITORS

THIS_COMPUTER: Final[str] = socket.gethostname()


@dataclass(frozen=True)
class AdmissionCase:
    exposure: Exposure
    peer: str
    host: str
    admitted: bool


ADMISSION_CASES: Final[tuple[AdmissionCase, ...]] = (
    AdmissionCase(Exposure.LOCAL, "127.0.0.1", "localhost", admitted=True),
    AdmissionCase(Exposure.LOCAL, "::1", "::1", admitted=True),
    AdmissionCase(Exposure.LOCAL, "::ffff:127.0.0.1", "127.0.0.1", admitted=True),
    AdmissionCase(Exposure.LOCAL, "127.0.0.1", "rebound.example", admitted=False),
    AdmissionCase(Exposure.LOCAL, "192.168.1.20", "192.168.1.10", admitted=False),
    AdmissionCase(Exposure.NETWORK, "127.0.0.1", "localhost", admitted=True),
    AdmissionCase(Exposure.NETWORK, "192.168.1.20", "192.168.1.10", admitted=True),
    AdmissionCase(Exposure.NETWORK, "10.0.0.7", THIS_COMPUTER, admitted=True),
    AdmissionCase(Exposure.NETWORK, "fe80::1", f"{THIS_COMPUTER}.local", admitted=True),
    AdmissionCase(Exposure.NETWORK, "::ffff:192.168.1.20", "192.168.1.10", admitted=True),
    AdmissionCase(Exposure.NETWORK, "192.168.1.20", "rebound.example", admitted=False),
    AdmissionCase(Exposure.NETWORK, "127.0.0.1", "192.168.1.10", admitted=True),
    AdmissionCase(Exposure.NETWORK, "127.0.0.1", "rebound.example", admitted=False),
    AdmissionCase(Exposure.LOCAL, "127.0.0.1", "192.168.1.10", admitted=False),
    AdmissionCase(Exposure.NETWORK, "198.18.0.1", "192.168.1.10", admitted=False),
    AdmissionCase(Exposure.NETWORK, "203.0.113.9", "192.168.1.10", admitted=False),
    AdmissionCase(Exposure.NETWORK, "testclient", "192.168.1.10", admitted=False),
    AdmissionCase(Exposure.PUBLIC, "203.0.113.9", "site.example", admitted=True),
)


def _policy(exposure: Exposure) -> ServingPolicy:
    visitors = SITE_VISITORS if exposure is Exposure.PUBLIC else None
    return ServingPolicy.of(ServerConfig(exposure=exposure, visitors=visitors))


@pytest.mark.parametrize(
    "case", ADMISSION_CASES, ids=lambda case: f"{case.exposure.value}: {case.peer} naming {case.host}"
)
def test_a_request_is_answered_as_its_exposure_admits_it(case: AdmissionCase) -> None:
    assert _policy(case.exposure).admits(case.peer, case.host) is case.admitted


@pytest.mark.parametrize("exposure", list(Exposure))
def test_a_request_naming_no_host_or_address_is_answered_by_a_site_alone(exposure: Exposure) -> None:
    assert _policy(exposure).admits(None, "localhost") is (exposure is Exposure.PUBLIC)
    assert _policy(exposure).admits("127.0.0.1", None) is (exposure is Exposure.PUBLIC)


@pytest.mark.parametrize(
    ("exposure", "host", "binds"),
    [
        (Exposure.LOCAL, "127.0.0.1", True),
        (Exposure.LOCAL, "localhost", True),
        (Exposure.LOCAL, "0.0.0.0", False),
        (Exposure.LOCAL, "192.168.1.10", False),
        (Exposure.NETWORK, "0.0.0.0", True),
        (Exposure.PUBLIC, "0.0.0.0", True),
    ],
)
def test_a_server_listens_only_where_its_exposure_reaches(exposure: Exposure, host: str, binds: bool) -> None:
    assert _policy(exposure).binds(host) is binds


def test_a_site_shows_the_catalog_and_nothing_of_the_computer_or_the_person_behind_it() -> None:
    site = _policy(Exposure.PUBLIC)

    assert not (site.shows_paths or site.reports_file_availability or site.names_internals)
    assert not (site.shows_curation or site.shows_reviewers or site.serves_uncataloged_audio or site.serves_docs)
    assert site.requires_secure_transport
    assert site.visitor_limits == SITE_VISITORS
    assert (site.permits_site, site.permits_serve, site.permits_desktop_app) == (True, False, False)


@pytest.mark.parametrize("exposure", [Exposure.LOCAL, Exposure.NETWORK])
def test_a_library_at_home_shows_everything_it_holds(exposure: Exposure) -> None:
    home = _policy(exposure)

    assert home.shows_paths and home.reports_file_availability and home.names_internals
    assert home.shows_curation and home.shows_reviewers and home.serves_uncataloged_audio and home.serves_docs
    assert not home.requires_secure_transport
    assert home.visitor_limits is None
    assert (home.permits_site, home.permits_serve, home.permits_desktop_app) == (False, True, True)


def test_renders_are_capped_wherever_anyone_but_this_computer_asks() -> None:
    assert _policy(Exposure.LOCAL).concurrent_morphs is None
    assert _policy(Exposure.NETWORK).concurrent_morphs == HOME_CONCURRENT_MORPHS
    assert _policy(Exposure.PUBLIC).concurrent_morphs == SITE_VISITORS.concurrent_morphs


@pytest.mark.parametrize(
    ("exposure", "origin", "host", "admitted"),
    [
        (Exposure.LOCAL, None, "localhost", True),
        (Exposure.LOCAL, "http://localhost:5173", "127.0.0.1", True),
        (Exposure.LOCAL, "http://attacker.example", "localhost", False),
        (Exposure.LOCAL, "null", "localhost", False),
        (Exposure.NETWORK, "http://192.168.1.10:27440", "192.168.1.10", True),
        (Exposure.NETWORK, "http://attacker.example", "192.168.1.10", False),
        (Exposure.NETWORK, "http://192.168.1.10", None, False),
        (Exposure.PUBLIC, "http://attacker.example", "site.example", True),
    ],
)
def test_a_page_elsewhere_is_turned_away_from_a_library_at_home(
    exposure: Exposure, origin: str | None, host: str | None, admitted: bool
) -> None:
    assert _policy(exposure).admits_page(origin, host) is admitted
