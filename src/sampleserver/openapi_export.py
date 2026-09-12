from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from sampleserver.app import create_app

UNUSED_DATABASE_URL: Final[str] = "postgresql+psycopg://unused/unused"
UNUSED_LIBRARY_ROOT: Final[Path] = Path("unused-library")
UNUSED_INFERENCE_URL: Final[str] = "http://unused:8010"


def main() -> None:
    """Print the app's OpenAPI schema as JSON, for the frontend's `openapi-typescript` step.

    Building the app never opens its database, reads from its library root or dials the
    inference process, so the stand-in values here are never touched.
    """
    application = create_app(UNUSED_DATABASE_URL, UNUSED_LIBRARY_ROOT, UNUSED_INFERENCE_URL)
    print(json.dumps(application.openapi()))
