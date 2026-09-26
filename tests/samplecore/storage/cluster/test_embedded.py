from __future__ import annotations

import json
import shutil
import socket
import stat
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from samplecore.models.service_role import ServiceRole
from samplecore.storage.cluster.embedded import binaries
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

LOOPBACK: Final[str] = "127.0.0.1"

pytestmark = pytest.mark.usefixtures("worker_cluster_port")


@pytest.fixture
def running_cluster(tmp_path: Path) -> Iterator[EmbeddedCluster]:
    cluster = EmbeddedCluster(tmp_path)
    cluster.ensure_running(own_programs=True)
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

    assert running_cluster.ensure_running(own_programs=True) == managed_catalog_url(running_cluster.directory.parent)
    assert running_cluster.is_running


def test_a_cluster_whose_port_another_program_holds_moves_to_a_free_one(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind((LOOPBACK, 0))
        holder.listen()
        held = ClusterState(port=holder.getsockname()[1], password="secret")

        moved = claim_port(tmp_path, held)

    assert moved.port != held.port
    assert read_cluster_state(tmp_path) == moved


@pytest.mark.skipif(sys.platform == "win32", reason="Windows keeps a running program's files from being deleted")
def test_a_server_left_running_on_a_removed_installations_programs_is_restarted_on_these(tmp_path: Path) -> None:
    """The server an earlier installation started keeps running after that installation is removed, and fails
    the moment it loads a part of itself from the folder that is gone, a procedural language among them."""
    these_programs = binaries.program_path(binaries.PostgresProgram.PG_CTL).parent
    removed_installation = tmp_path / "removed-installation" / these_programs.parent.name
    shutil.copytree(these_programs.parent, removed_installation)
    cluster = EmbeddedCluster(tmp_path / "library")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(binaries, "_binary_directory", lambda: removed_installation / these_programs.name)
        cluster.ensure_running(own_programs=True)
    shutil.rmtree(removed_installation)
    owner_url = managed_catalog_url(cluster.directory.parent)
    try:
        with closing(connect(owner_url, read_only=True)) as connection, pytest.raises(DBAPIError):
            connection.execute(text("DO $$ BEGIN END $$"))

        cluster.ensure_running(own_programs=True)

        with closing(connect(owner_url, read_only=True)) as connection:
            connection.execute(text("DO $$ BEGIN END $$"))
            server_programs = connection.execute(
                text("SELECT setting FROM pg_catalog.pg_config WHERE name = 'BINDIR'")
            ).scalar_one()
        assert Path(server_programs).resolve() == these_programs.resolve()
    finally:
        cluster.stop()
