from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from samplecore.cli_parsing import command_parser


def parse_schema_arguments(argv: list[str], *, prog: str, description: str) -> argparse.Namespace:
    """A schema command's arguments: the file to write the schema to, standard output when left out."""
    parser = command_parser(prog=prog, description=description)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="The file to write the schema to, as UTF-8; standard output if left out.",
    )
    return parser.parse_args(argv)


def export_schema(schema: dict[str, Any], output: Path | None) -> None:
    """Print an OpenAPI schema as JSON, or write it to ``output``, for the frontend's `openapi-typescript` step.

    Raises:
        SystemExit: the output file cannot be written, with one line saying why.
    """
    document = json.dumps(schema)
    if output is None:
        print(document)
        return
    try:
        output.write_text(f"{document}\n", encoding="utf-8")
    except OSError as error:
        sys.exit(f"Wrote nothing: {output} cannot be written ({error.strerror}).")
