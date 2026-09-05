from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from sampleserver.app import create_app

UNUSED_DATABASE_PATH: Final[Path] = Path("unused.duckdb")
UNUSED_LIBRARY_ROOT: Final[Path] = Path("unused-library")


def main() -> None:
    """Print the app's OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    Building the app never opens its database or reads from its library root, so
    `UNUSED_DATABASE_PATH`/`UNUSED_LIBRARY_ROOT` are never touched here.
    """
    application = create_app(UNUSED_DATABASE_PATH, UNUSED_LIBRARY_ROOT)
    print(json.dumps(application.openapi()))
