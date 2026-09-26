from __future__ import annotations

import sys
import time
from enum import StrEnum, unique
from importlib.metadata import version
from typing import Final

import httpx
from pydantic import BaseModel, ValidationError

from samplecore.models.base import FROZEN
from samplelibrary.environment import PACKAGE_NAME

INSTALLATION_ROUTE: Final[str] = "/installation"
QUIT_ROUTE: Final[str] = "/quit"
QUIT_POLL_SECONDS: Final[float] = 0.25


class Installation(BaseModel):
    """Which installation of the application a running server belongs to: its version and its Python environment.

    Each launcher installs its own environment, so the processor launcher, the NVIDIA one and a
    source checkout each report a different one, and so does every new version.
    """

    model_config = FROZEN

    version: str
    environment: str


@unique
class PortHolder(StrEnum):
    """Who answers on the port a start of the application is about to listen on."""

    NOBODY = "nobody"
    THIS_INSTALLATION = "this installation"
    OTHER_INSTALLATION = "other installation"
    OTHER_PROGRAM = "other program"


def this_installation() -> Installation:
    return Installation(version=version(PACKAGE_NAME), environment=sys.prefix)


def port_holder(setup: httpx.Client) -> PortHolder:
    """Who answers at the setup routes ``setup`` is based at, told apart by the installation the answer names."""
    try:
        response = setup.get(INSTALLATION_ROUTE)
    except httpx.ConnectError:
        return PortHolder.NOBODY
    except httpx.HTTPError:
        return PortHolder.OTHER_PROGRAM
    if not response.is_success:
        return PortHolder.OTHER_PROGRAM
    try:
        running = Installation.model_validate_json(response.content)
    except ValidationError:
        return PortHolder.OTHER_PROGRAM
    return PortHolder.THIS_INSTALLATION if running == this_installation() else PortHolder.OTHER_INSTALLATION


def close_running(setup: httpx.Client, *, wait_seconds: float) -> bool:
    """Ask the application answering at ``setup`` to quit, and whether its port came free within ``wait_seconds``.

    The application answers a quit once its library is closed, with its build, renderer and managed
    database stopped, and lets its port go right after, so a start that finds the port free opens
    the same library at once.
    """
    deadline = time.monotonic() + wait_seconds
    try:
        response = setup.post(QUIT_ROUTE, timeout=wait_seconds)
    except httpx.TimeoutException:
        return False
    if not response.is_success:
        return False
    while time.monotonic() < deadline:
        if port_holder(setup) is PortHolder.NOBODY:
            return True
        time.sleep(QUIT_POLL_SECONDS)
    return False
