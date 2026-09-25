from __future__ import annotations

import tomllib
from pathlib import Path


def project_version(project_file: Path) -> str:
    """The version a project's `pyproject.toml` declares."""
    with project_file.open("rb") as file:
        return str(tomllib.load(file)["project"]["version"])
