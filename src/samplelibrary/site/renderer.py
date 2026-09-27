from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import httpx

from samplecore.config import (
    CONFIG_PATH_ENVIRONMENT_VARIABLE,
    CURATION_DATABASE_URL_ENVIRONMENT_VARIABLE,
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE,
    SERVER_DATABASE_URL_ENVIRONMENT_VARIABLE,
    InferenceConfig,
)
from samplecore.process_pool import SINGLE_THREAD_ENVIRONMENT
from samplecore.storage.cluster.provisioning import ADMIN_URL_ENVIRONMENT_VARIABLE
from samplelibrary.children import ChildProcess, samplelibrary_command
from samplelibrary.site.messages import RENDERER_DID_NOT_START, RENDERER_ENDED_AT_START

RENDERER_NAME: Final[str] = "morph renderer"
RENDERER_COMMAND: Final[tuple[str, ...]] = ("morph", "serve")
STATUS_PATH: Final[str] = "/morph/status"
READY_SECONDS: Final[float] = 300.0
POLL_SECONDS: Final[float] = 0.5
STATUS_TIMEOUT_SECONDS: Final[float] = 2.0
# The renderer opens no database, so it is handed no connection to one.
DATABASE_VARIABLES: Final[tuple[str, ...]] = (
    DATABASE_URL_ENVIRONMENT_VARIABLE,
    SERVER_DATABASE_URL_ENVIRONMENT_VARIABLE,
    CURATION_DATABASE_URL_ENVIRONMENT_VARIABLE,
    ADMIN_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE,
    PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE,
)


class RendererDidNotStartError(Exception):
    """Raised when the site's renderer ends, or answers no status request, before it is ready."""


def site_renderer(inference: InferenceConfig, *, environment: Mapping[str, str], config_path: Path) -> ChildProcess:
    """The site's morph renderer: `morph serve` on the configured loopback address, its output joining the site's.

    It reads the site's config, holds no database connection in its environment, and computes on one
    thread per numerical library, so a render shares the container with the server answering pages.
    """
    command = samplelibrary_command(*RENDERER_COMMAND, "--host", inference.host, "--port", str(inference.port))
    renderer_environment = {
        **{name: value for name, value in environment.items() if name not in DATABASE_VARIABLES},
        **SINGLE_THREAD_ENVIRONMENT,
        CONFIG_PATH_ENVIRONMENT_VARIABLE: str(config_path),
    }
    return ChildProcess(RENDERER_NAME, command, environment=renderer_environment, log_path=None)


def wait_until_answering(renderer: ChildProcess, inference: InferenceConfig) -> None:
    """Wait for the renderer to answer its status route, which it does once its route is loaded and warmed.

    Raises:
        RendererDidNotStartError: the renderer ended, or stayed silent for `READY_SECONDS`.
    """
    deadline = time.monotonic() + READY_SECONDS
    with httpx.Client(base_url=inference.url, timeout=STATUS_TIMEOUT_SECONDS) as client:
        while time.monotonic() < deadline:
            if not renderer.is_running:
                raise RendererDidNotStartError(RENDERER_ENDED_AT_START)
            try:
                if client.get(STATUS_PATH).is_success:
                    return
            except httpx.TransportError:
                pass
            time.sleep(POLL_SECONDS)
    raise RendererDidNotStartError(RENDERER_DID_NOT_START.format(seconds=READY_SECONDS))
