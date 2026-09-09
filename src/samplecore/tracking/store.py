from __future__ import annotations

from pathlib import Path
from typing import Final

TRACKING_DATABASE_NAME: Final[str] = "mlflow.db"
ARTIFACT_DIRECTORY_NAME: Final[str] = "mlflow-artifacts"


def tracking_uri(library_root: Path) -> str:
    """Where recorded runs are kept, as the URI a tracking client connects to.

    A database rather than a directory of files, so runs can be queried by parameter and metric and
    so a fitted model can be promoted by name and version. It sits beside the audio under the
    library root, which is where everything this project produces and nothing it version-controls
    already lives.
    """
    return f"sqlite:///{library_root / TRACKING_DATABASE_NAME}"


def artifact_root(library_root: Path) -> Path:
    """Where files a run produced are kept.

    Stated to the tracker explicitly at the moment an experiment is created, because a client left
    to itself writes artifacts beneath the working directory -- which for this project is the
    repository, the one place runs are held out of.
    """
    return library_root / ARTIFACT_DIRECTORY_NAME
