from __future__ import annotations

import secrets
import socket
import sys
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_bytes_atomically

CLUSTER_DIRECTORY_NAME: Final[str] = "postgres"
DATA_DIRECTORY_NAME: Final[str] = "data"
STATE_FILE_NAME: Final[str] = "cluster.json"
LOG_FILE_NAME: Final[str] = "server.log"
MANAGED_ROLE: Final[str] = "samplelibrary"
MANAGED_DATABASE: Final[str] = "samplelibrary"
MANAGED_HOST: Final[str] = "127.0.0.1"
PREFERRED_MANAGED_PORT: Final[int] = 54329
PASSWORD_BYTES: Final[int] = 24
PRIVATE_FILE_MODE: Final[int] = 0o600
MAXIMUM_PORT: Final[int] = 65535


class ManagedClusterMissingError(Exception):
    """Raised when a library relies on its managed database before that database has been set up."""


class ClusterState(BaseModel):
    """Where a library's managed Postgres listens and the password its one role logs in with.

    Written once, when the cluster is created, and read by every process that opens the catalog,
    so the launcher, the pipeline's steps and a command run by hand all reach the same server.
    """

    model_config = FROZEN

    port: int = Field(ge=1, le=MAXIMUM_PORT)
    password: str = Field(min_length=1)

    @property
    def catalog_url(self) -> str:
        """The URL every connection to the library's catalog opens."""
        return f"postgresql+psycopg://{MANAGED_ROLE}:{self.password}@{MANAGED_HOST}:{self.port}/{MANAGED_DATABASE}"


def cluster_directory(library_root: Path) -> Path:
    """The folder holding a library's managed Postgres: its data, its state and its server log."""
    return library_root / CLUSTER_DIRECTORY_NAME


def state_path(library_root: Path) -> Path:
    return cluster_directory(library_root) / STATE_FILE_NAME


def read_cluster_state(library_root: Path) -> ClusterState:
    """The managed cluster's state as it was written when the cluster was created.

    Raises:
        ManagedClusterMissingError: the library holds no managed cluster yet.
    """
    path = state_path(library_root)
    if not path.is_file():
        raise ManagedClusterMissingError(
            f"The library at {library_root} has no database yet. "
            "Start the SampleLibrary app or run `samplelibrary setup database` to create one."
        )
    return ClusterState.model_validate_json(path.read_text(encoding="utf-8"))


def managed_catalog_url(library_root: Path) -> str:
    """The catalog URL of a library whose database the application manages itself.

    Raises:
        ManagedClusterMissingError: the library holds no managed cluster yet.
    """
    return read_cluster_state(library_root).catalog_url


def create_cluster_state(library_root: Path) -> ClusterState:
    """Choose the port and the password of a new cluster and record them, readable by their owner alone.

    The preferred port keeps a library's address stable from one machine to the next, and a free one
    the system hands out takes its place when another program already listens there.
    """
    state = ClusterState(port=_free_port(), password=secrets.token_urlsafe(PASSWORD_BYTES))
    _write_cluster_state(library_root, state)
    return state


def claim_port(library_root: Path, state: ClusterState) -> ClusterState:
    """The state a stopped cluster starts under: its recorded port while that is free, a new one recorded otherwise."""
    if _port_is_free(state.port):
        return state
    moved = state.model_copy(update={"port": _free_port()})
    _write_cluster_state(library_root, moved)
    return moved


def _write_cluster_state(library_root: Path, state: ClusterState) -> None:
    path = state_path(library_root)
    write_bytes_atomically(path, state.model_dump_json().encode("utf-8"))
    if sys.platform != "win32":
        path.chmod(PRIVATE_FILE_MODE)


def _free_port() -> int:
    if _port_is_free(PREFERRED_MANAGED_PORT):
        return PREFERRED_MANAGED_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((MANAGED_HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((MANAGED_HOST, port))
        except OSError:
            return False
        return True
