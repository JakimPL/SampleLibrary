from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

from sqlalchemy.engine import make_url

from samplecore.config import PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE, LibraryConfig
from samplecore.passwords import MINIMUM_SERVICE_PASSWORD_LENGTH
from samplecore.ports import MAXIMUM_PORT, MINIMUM_PORT
from samplecore.storage.audio_store import OBJECTS_DIRECTORY_NAME
from samplecore.storage.cluster.provisioning import ADMIN_URL_ENVIRONMENT_VARIABLE
from sampleripper.site.messages import (
    BAD_PORT,
    CREDENTIAL_BEYOND_READER,
    NO_AUDIO_STORE,
    NO_PORT,
    NO_READER,
    NOT_PUBLIC,
    PORT_TAKEN_BY_RENDERER,
    RENDERER_BEYOND_THIS_COMPUTER,
    WEAK_READER_PASSWORD,
)
from sampleserver.addresses import names_loopback
from sampleserver.policy import ServingPolicy

PORT_ENVIRONMENT_VARIABLE: Final[str] = "PORT"
# The connections that may change something, which a site's own environment holds none of.
CHANGING_CONNECTION_VARIABLES: Final[tuple[str, ...]] = (
    ADMIN_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE,
)


class SiteRefusedError(Exception):
    """Raised when a site may not start as configured; ``problems`` names each reason, one sentence apiece."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(" ".join(problems))
        self.problems = problems


def site_port(environment: Mapping[str, str]) -> int:
    """The port the platform names in ``$PORT`` for the site to listen on.

    Raises:
        SiteRefusedError: ``$PORT`` is missing, or names no port.
    """
    raw = environment.get(PORT_ENVIRONMENT_VARIABLE)
    if not raw:
        raise SiteRefusedError((NO_PORT,))
    try:
        port = int(raw)
    except ValueError as error:
        raise SiteRefusedError((BAD_PORT.format(value=raw),)) from error
    if not MINIMUM_PORT <= port <= MAXIMUM_PORT:
        raise SiteRefusedError((BAD_PORT.format(value=raw),))
    return port


def admit_site(config: LibraryConfig, *, port: int, environment: Mapping[str, str]) -> None:
    """Insist that the configuration serves the library to anyone, with the reader's credentials alone.

    A site answers anyone on the internet, so it holds nothing that could change the catalog: no
    owner, curator, administrator or publishing connection, from the file or the environment, and a
    reader whose password was generated rather than chosen. Its renderer listens on this computer
    alone, on a port apart from the site's, and its audio store is in place.

    Raises:
        SiteRefusedError: naming every way the configuration falls short of that.
    """
    problems = (
        *_exposure(config),
        *_credentials(config, environment=environment),
        *_renderer(config, port=port),
        *_audio_store(config),
    )
    if problems:
        raise SiteRefusedError(problems)


def _exposure(config: LibraryConfig) -> tuple[str, ...]:
    return () if ServingPolicy.of(config.server).permits_site else (NOT_PUBLIC,)


def _credentials(config: LibraryConfig, *, environment: Mapping[str, str]) -> tuple[str, ...]:
    beyond = [
        *(setting for setting in ("database_url", "curation_database_url") if setting in config.database_urls()),
        *(variable for variable in CHANGING_CONNECTION_VARIABLES if environment.get(variable)),
    ]
    problems = [CREDENTIAL_BEYOND_READER.format(name=name) for name in beyond]
    if config.server_database_url is None:
        problems.append(NO_READER)
    elif len(make_url(config.server_database_url).password or "") < MINIMUM_SERVICE_PASSWORD_LENGTH:
        problems.append(WEAK_READER_PASSWORD.format(length=MINIMUM_SERVICE_PASSWORD_LENGTH))
    return tuple(problems)


def _renderer(config: LibraryConfig, *, port: int) -> tuple[str, ...]:
    problems = []
    if not names_loopback(config.inference.host):
        problems.append(RENDERER_BEYOND_THIS_COMPUTER)
    if config.inference.port == port:
        problems.append(PORT_TAKEN_BY_RENDERER)
    return tuple(problems)


def _audio_store(config: LibraryConfig) -> tuple[str, ...]:
    store = config.library_root / OBJECTS_DIRECTORY_NAME
    readable = store.is_dir() and os.access(store, os.R_OK | os.X_OK)
    return () if readable else (NO_AUDIO_STORE.format(path=store),)
