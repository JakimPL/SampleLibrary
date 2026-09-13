from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

from sampleserver.app import create_app

UNUSED_DATABASE_URL: Final[str] = "postgresql+psycopg://unused/unused"
UNUSED_LIBRARY_ROOT: Final[Path] = Path("unused-library")
UNUSED_INFERENCE_URL: Final[str] = "http://unused:8010"


def main(argv: list[str], *, prog: str) -> None:
    """Print or write the app's OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    Building the app never opens its database, reads from its library root or dials the
    inference process, so the stand-in values here are never touched.
    """
    arguments = _parse_arguments(argv, prog=prog)
    application = create_app(UNUSED_DATABASE_URL, UNUSED_LIBRARY_ROOT, UNUSED_INFERENCE_URL)
    schema = json.dumps(application.openapi())
    if arguments.output is None:
        print(schema)
    else:
        arguments.output.write_text(f"{schema}\n", encoding="utf-8")


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=prog, description="Print the API's OpenAPI schema as JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="The file to write the schema to, as UTF-8; standard output if left out.",
    )
    return parser.parse_args(argv)
