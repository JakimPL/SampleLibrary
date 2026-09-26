from __future__ import annotations

import json
import os
import socket
import stat
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import inspect

from samplecore.models.service_role import ServiceRole
from samplecore.storage.cluster.embedded import state as cluster_state
from samplecore.storage.cluster.embedded.server import EmbeddedCluster
from samplecore.storage.cluster.embedded.state import (
    PRIVATE_FILE_MODE,
    ClusterState,
    ManagedClusterMissingError,
    claim_port,
    create_cluster_state,
    managed_catalog_url,
    managed_service_url,
    read_cluster_state,
    roles_path,
    state_path,
)
from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import connect

WORKER_ENVIRONMENT_VARIABLE: Final[str] = "PYTEST_XDIST_WORKER"
WORKER_PREFIX: Final[str] = "gw"
FIRST_WORKER: Final[str] = "gw0"
WORKER_PORT_BASE: Final[int] = 25432
LOOPBACK: Final[str] = "127.0.0.1"


@pytest.fixture(autouse=True)
def worker_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each test worker a preferred port of its own, so clusters that workers start side by side each listen on theirs.

    The ports sit below the range Linux, macOS and Windows hand out to outgoing connections, which
    keeps the database connections the tests open off them between a cluster's port check and its start.
    """
    worker = int(os.environ.get(WORKER_ENVIRONMENT_VARIABLE, FIRST_WORKER).removeprefix(WORKER_PREFIX))
    monkeypatch.setattr(cluster_state, "PREFERRED_MANAGED_PORT", WORKER_PORT_BASE + worker)


@pytest.fixture
def running_cluster(tmp_path: Path) -> Iterator[EmbeddedCluster]:
    cluster = EmbeddedCluster(tmp_path)
    cluster.ensure_running()
    try:
        yield cluster
    finally:
        cluster.stop()


def test_a_library_without_a_cluster_names_what_creates_one(tmp_path: Path) -> None:
    with pytest.raises(ManagedClusterMissingError, match="setup database"):
        managed_catalog_url(tmp_path)


def test_the_recorded_state_round_trips_and_names_the_loopback_address(tmp_path: Path) -> None:
    state = create_cluster_state(tmp_path)

    assert read_cluster_state(tmp_path) == state
    assert f"@127.0.0.1:{state.port}/" in state.catalog_url
    assert json.loads(state_path(tmp_path).read_text(encoding="utf-8"))["password"] == state.password


@pytest.mark.skipif(sys.platform == "win32", reason="Windows keeps no POSIX file modes")
def test_a_started_cluster_keeps_its_service_roles_passwords_to_its_owner(running_cluster: EmbeddedCluster) -> None:
    library_root = running_cluster.directory.parent

    assert stat.S_IMODE(roles_path(library_root).stat().st_mode) == PRIVATE_FILE_MODE
    with closing(connect(managed_service_url(library_root, ServiceRole.READER), read_only=True)) as connection:
        assert inspect(connection).has_table("sample")


def test_a_started_cluster_holds_the_catalog_and_the_curation_schema(running_cluster: EmbeddedCluster) -> None:
    connection = connect(managed_catalog_url(running_cluster.directory.parent), read_only=True)
    try:
        inspector = inspect(connection)
        assert "sample" in inspector.get_table_names()
        assert CURATION_SCHEMA in inspector.get_schema_names()
    finally:
        connection.close()


def test_a_cluster_starts_again_after_it_stops_at_the_address_it_records(running_cluster: EmbeddedCluster) -> None:
    running_cluster.stop()
    assert not running_cluster.is_running

    assert running_cluster.ensure_running() == managed_catalog_url(running_cluster.directory.parent)
    assert running_cluster.is_running


def test_a_cluster_whose_port_another_program_holds_moves_to_a_free_one(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind((LOOPBACK, 0))
        holder.listen()
        held = ClusterState(port=holder.getsockname()[1], password="secret")

        moved = claim_port(tmp_path, held)

    assert moved.port != held.port
    assert read_cluster_state(tmp_path) == moved
