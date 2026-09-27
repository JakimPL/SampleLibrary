from __future__ import annotations

import sys
from contextlib import suppress
from enum import StrEnum, unique
from importlib.metadata import version
from typing import Final

import httpx
from pydantic import BaseModel, ValidationError

from samplecore.models.base import FROZEN
from sampleripper.environment import PACKAGE_NAME

INSTALLATION_ROUTE: Final[str] = "/installation"
QUIT_ROUTE: Final[str] = "/quit"


class Installation(BaseModel):
    """Which installation of the application a running server belongs to: its version and its Python environment.

    Each launcher installs its own environment, so the processor launcher, the NVIDIA one and a
    source checkout each report a different one, and so does every new version.
    """

    model_config = FROZEN

    version: str
    environment: str


@unique
class Reply(StrEnum):
    """How the application at a recorded address answers a start asking who it is."""

    SAME_INSTALLATION = "same installation"
    OTHER_INSTALLATION = "other installation"
    CLOSED = "closed"
    SILENT = "silent"


def this_installation() -> Installation:
    return Installation(version=version(PACKAGE_NAME), environment=sys.prefix)


def reply_at(setup: httpx.Client) -> Reply:
    """How the application at the setup routes ``setup`` is based at answers.

    A refused or dropped connection means its server has closed its port on the way out; a
    connection it takes without answering means it has stopped responding. Any answer other than
    this installation's own comes from another installation.
    """
    try:
        response = setup.get(INSTALLATION_ROUTE)
    except httpx.TimeoutException:
        return Reply.SILENT
    except httpx.TransportError:
        return Reply.CLOSED
    if not response.is_success:
        return Reply.OTHER_INSTALLATION
    try:
        running = Installation.model_validate_json(response.content)
    except ValidationError:
        return Reply.OTHER_INSTALLATION
    return Reply.SAME_INSTALLATION if running == this_installation() else Reply.OTHER_INSTALLATION


def ask_to_quit(setup: httpx.Client, *, seconds: float) -> None:
    """Ask the application at ``setup`` to quit, waiting up to ``seconds`` for it to close its library.

    Its lock tells when it has ended, so a request the application leaves unanswered or drops as
    it goes changes nothing for the start waiting on it.
    """
    with suppress(httpx.HTTPError):
        setup.post(QUIT_ROUTE, timeout=seconds)
