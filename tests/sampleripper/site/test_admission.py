from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pytest

from samplecore.config import (
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE,
    LibraryConfig,
    parse_config,
)
from samplecore.storage.cluster.provisioning import ADMIN_URL_ENVIRONMENT_VARIABLE
from sampleripper.site.admission import SiteRefusedError, admit_site, site_port, site_warnings
from sampleripper.site.messages import (
    CREDENTIAL_BEYOND_READER,
    NO_AUDIO,
    NO_PORT,
    NO_READER,
    NO_READER_HOST,
    NOT_PUBLIC,
    PORT_TAKEN_BY_RENDERER,
    RENDERER_BEYOND_THIS_COMPUTER,
    UNREADABLE_AUDIO_STORE,
    WEAK_READER_PASSWORD,
)
from tests.sampleserver.conftest import SITE_VISITORS_TABLE

SITE_PORT: Final[int] = 8000
GENERATED_PASSWORD: Final[str] = "q" * 32
READER_URL: Final[str] = f"postgresql+psycopg://sampleripper_reader:{GENERATED_PASSWORD}@postgres.internal:5432/railway"


@dataclass(frozen=True)
class SiteConfig:
    """The pieces of a site's config a test changes, each as it is written into the file."""

    exposure: str = "public"
    library: dict[str, str] = field(default_factory=lambda: {"server_database_url": READER_URL})
    inference_url: str = "http://127.0.0.1:8010"


def _site_config(tmp_path: Path, pieces: SiteConfig, monkeypatch: pytest.MonkeyPatch) -> LibraryConfig:
    for variable in (DATABASE_URL_ENVIRONMENT_VARIABLE, ADMIN_URL_ENVIRONMENT_VARIABLE):
        monkeypatch.delenv(variable, raising=False)
    library_root = tmp_path / "library"
    (library_root / "objects").mkdir(parents=True, exist_ok=True)
    settings = "".join(f'{name} = "{value}"\n' for name, value in pieces.library.items())
    visitors = SITE_VISITORS_TABLE if pieces.exposure == "public" else ""
    content = (
        f'[library]\nlibrary_root = "{library_root.as_posix()}"\n{settings}'
        f'[inference]\nurl = "{pieces.inference_url}"\n'
        f'[server]\nexposure = "{pieces.exposure}"\n{visitors}'
    )
    return parse_config(content, tmp_path / "config.toml")


def _problems(
    config: LibraryConfig, *, port: int = SITE_PORT, environment: dict[str, str] | None = None
) -> tuple[str, ...]:
    try:
        admit_site(config, port=port, environment=environment or {})
    except SiteRefusedError as refusal:
        return refusal.problems
    return ()


def test_a_site_with_the_readers_credentials_alone_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _problems(_site_config(tmp_path, SiteConfig(), monkeypatch)) == ()


def test_a_library_at_home_is_no_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _site_config(tmp_path, SiteConfig(exposure="local"), monkeypatch)

    assert NOT_PUBLIC in _problems(config)


@pytest.mark.parametrize(
    "setting",
    [
        ("database_url", "postgresql+psycopg://sampleripper:owner-secret@postgres.internal/railway"),
        ("curation_database_url", "postgresql+psycopg://sampleripper_curator:curator@postgres.internal/railway"),
    ],
    ids=("the owner", "the curator"),
)
def test_a_site_holding_a_connection_that_changes_the_catalog_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: tuple[str, str]
) -> None:
    name, url = setting
    config = _site_config(tmp_path, SiteConfig(library={"server_database_url": READER_URL, name: url}), monkeypatch)

    assert CREDENTIAL_BEYOND_READER.format(name=name) in _problems(config)


@pytest.mark.parametrize("variable", [ADMIN_URL_ENVIRONMENT_VARIABLE, PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE])
def test_a_site_whose_environment_names_a_changing_connection_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    config = _site_config(tmp_path, SiteConfig(), monkeypatch)

    problems = _problems(config, environment={variable: "postgresql+psycopg://postgres:x@proxy.example/railway"})

    assert CREDENTIAL_BEYOND_READER.format(name=variable) in problems


def test_an_owner_named_in_the_environment_reaches_the_site_as_its_setting_and_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, "postgresql+psycopg://postgres:x@postgres.internal/railway")
    config = parse_config(
        f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\nserver_database_url = "{READER_URL}"\n'
        f'[server]\nexposure = "public"\n{SITE_VISITORS_TABLE}',
        tmp_path / "config.toml",
    )
    (tmp_path / "library" / "objects").mkdir(parents=True)

    assert CREDENTIAL_BEYOND_READER.format(name="database_url") in _problems(config)


def test_a_site_naming_no_reader_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _site_config(tmp_path, SiteConfig(library={}), monkeypatch)

    assert NO_READER in _problems(config)


def test_a_reader_with_a_chosen_password_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weak = READER_URL.replace(GENERATED_PASSWORD, "change-me")
    config = _site_config(tmp_path, SiteConfig(library={"server_database_url": weak}), monkeypatch)

    assert WEAK_READER_PASSWORD.format(length=24) in _problems(config)


def test_a_reader_address_naming_no_host_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reference to another service that a platform leaves empty gives an address with nothing between @ and the port."""
    hostless = f"postgresql+psycopg://sampleripper_reader:{GENERATED_PASSWORD}@:5432/railway"
    config = _site_config(tmp_path, SiteConfig(library={"server_database_url": hostless}), monkeypatch)

    assert NO_READER_HOST in _problems(config)


def test_a_renderer_listening_beyond_this_computer_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _site_config(tmp_path, SiteConfig(inference_url="http://0.0.0.0:8010"), monkeypatch)

    assert RENDERER_BEYOND_THIS_COMPUTER in _problems(config)


def test_a_site_listening_on_the_renderers_port_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert PORT_TAKEN_BY_RENDERER in _problems(_site_config(tmp_path, SiteConfig(), monkeypatch), port=8010)


@pytest.mark.parametrize("store", ["missing", "empty"])
def test_a_site_without_its_audio_starts_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store: str
) -> None:
    """A platform's volume is filled through the running site, so the site starts and says what it lacks."""
    config = _site_config(tmp_path, SiteConfig(), monkeypatch)
    if store == "missing":
        (config.library_root / "objects").rmdir()

    assert _problems(config) == ()
    assert site_warnings(config) == (NO_AUDIO.format(path=config.library_root / "objects"),)


def test_a_site_with_its_audio_warns_of_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _site_config(tmp_path, SiteConfig(), monkeypatch)
    stored = config.library_root / "objects" / "ab" / ("ab" + "c" * 62 + ".wav")
    stored.parent.mkdir()
    stored.write_bytes(b"RIFF")

    assert site_warnings(config) == ()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every folder")
def test_a_site_whose_audio_store_it_cannot_read_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _site_config(tmp_path, SiteConfig(), monkeypatch)
    store = config.library_root / "objects"
    store.chmod(0)
    try:
        assert UNREADABLE_AUDIO_STORE.format(path=store) in _problems(config)
    finally:
        store.chmod(stat.S_IRWXU)


@pytest.mark.parametrize(("environment", "port"), [({"PORT": "8080"}, 8080)])
def test_the_port_comes_from_the_platform(environment: dict[str, str], port: int) -> None:
    assert site_port(environment) == port


@pytest.mark.parametrize("environment", [{}, {"PORT": ""}, {"PORT": "eighty"}, {"PORT": "70000"}])
def test_a_port_the_platform_names_no_port_is_refused(environment: dict[str, str]) -> None:
    with pytest.raises(SiteRefusedError) as refusal:
        site_port(environment)

    assert refusal.value.problems[0] == NO_PORT or "names no port" in refusal.value.problems[0]
