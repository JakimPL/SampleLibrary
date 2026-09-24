from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from samplecore.cli_parsing import command_parser
from samplelibrary.app.asgi import create_application
from samplelibrary.app.launcher import Launcher

UNUSED_CONFIG_PATH: Final[Path] = Path("unused-config.toml")
UNUSED_COMMAND: Final[tuple[str, ...]] = ("unused",)
DESCRIPTION: Final[str] = "Print the setup pages' OpenAPI schema as JSON, or write it to a file."


def main(argv: list[str], *, prog: str) -> None:
    """Print or write the setup routes' OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    Building the application reads no config file and starts nothing, so the stand-in values here are never used.

    Raises:
        SystemExit: the output file cannot be written, with one line saying why.
    """
    arguments = _parse_arguments(argv, prog=prog)
    launcher = Launcher(UNUSED_CONFIG_PATH, renderer_command=UNUSED_COMMAND, pipeline_command=UNUSED_COMMAND)
    schema = json.dumps(create_application(launcher, frontend_directory=None, on_ready=lambda: None).openapi())
    if arguments.output is None:
        print(schema)
        return
    try:
        arguments.output.write_text(f"{schema}\n", encoding="utf-8")
    except OSError as error:
        sys.exit(f"Wrote nothing: {arguments.output} cannot be written ({error.strerror}).")


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description=DESCRIPTION)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="The file to write the schema to, as UTF-8; standard output if left out.",
    )
    return parser.parse_args(argv)
