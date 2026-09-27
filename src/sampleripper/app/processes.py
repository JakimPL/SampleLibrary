from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.processes import HIDDEN_CONSOLE_FLAGS
from sampleripper.pipeline.devices import BuildDevice

DEVICE_PROBE_SECONDS: Final[float] = 120.0

_logger = logging.getLogger(__name__)


def probe_build_device(command: tuple[str, ...], *, config_path: Path) -> BuildDevice:
    """The device builds compute on, as ``command`` names it, or the processor where the command fails to say.

    The command imports torch, which the application's own process leaves out, so it runs apart.
    """
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=DEVICE_PROBE_SECONDS,
            env=child_environment(config_path),
            creationflags=HIDDEN_CONSOLE_FLAGS,
        )
        return BuildDevice.model_validate_json(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValidationError) as error:
        _logger.warning("Could not tell which device builds use, so they count on the processor: %s", error)
        return BuildDevice(card=None)


def child_environment(config_path: Path) -> dict[str, str]:
    """The environment of a program the application starts: its own, pointing at the application's config file."""
    return {**os.environ, CONFIG_PATH_ENVIRONMENT_VARIABLE: str(config_path)}
