from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.schema_export import export_schema, parse_schema_arguments
from samplecore.storage.service_roles import ServiceRole
from sampleserver.app import create_app

UNUSED_DATABASE_URL: Final[str] = "postgresql+psycopg://unused/unused"
UNUSED_LIBRARY_ROOT: Final[Path] = Path("unused-library")
UNUSED_INFERENCE_URL: Final[str] = "http://unused:8010"
DESCRIPTION: Final[str] = "Print the API's OpenAPI schema as JSON, or write it to a file."


def main(argv: list[str], *, prog: str) -> None:
    """Print or write the app's OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    The schema is a curator's, which holds every route a page may call; a page learns from the
    served app whether it may change labels. Building the app never opens its database, reads from
    its library root or dials the inference process, so the stand-in values here are never touched.

    Raises:
        SystemExit: the output file cannot be written, with one line saying why.
    """
    arguments = parse_schema_arguments(argv, prog=prog, description=DESCRIPTION)
    application = create_app(
        UNUSED_DATABASE_URL,
        UNUSED_LIBRARY_ROOT,
        UNUSED_INFERENCE_URL,
        role=ServiceRole.CURATOR,
        frontend_directory=None,
    )
    export_schema(application.openapi(), arguments.output)
