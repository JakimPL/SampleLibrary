from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.config import DEFAULT_SERVER_CONFIG
from samplecore.schema_export import export_schema, parse_schema_arguments
from samplelibrary.app.asgi import create_application
from samplelibrary.app.launcher import Launcher
from samplelibrary.app.listener import CLOSED_TO_THE_NETWORK
from sampleserver.policy import ServingPolicy

UNUSED_CONFIG_PATH: Final[Path] = Path("unused-config.toml")
UNUSED_COMMAND: Final[tuple[str, ...]] = ("unused",)
DESCRIPTION: Final[str] = "Print the setup pages' OpenAPI schema as JSON, or write it to a file."


def main(argv: list[str], *, prog: str) -> None:
    """Print or write the setup routes' OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    Building the application reads no config file and starts nothing, so the stand-in values here are never used.

    Raises:
        SystemExit: the output file cannot be written, with one line saying why.
    """
    arguments = parse_schema_arguments(argv, prog=prog, description=DESCRIPTION)
    launcher = Launcher(
        UNUSED_CONFIG_PATH,
        renderer_command=UNUSED_COMMAND,
        pipeline_command=UNUSED_COMMAND,
        device_command=UNUSED_COMMAND,
        home_network=CLOSED_TO_THE_NETWORK,
    )
    application = create_application(
        launcher, frontend_directory=None, on_ready=lambda: None, policy=ServingPolicy.of(DEFAULT_SERVER_CONFIG)
    )
    export_schema(application.openapi(), arguments.output)
