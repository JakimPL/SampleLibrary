from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import inspect

from samplecore.storage.cluster.embedded.server import EmbeddedCluster
from samplecore.storage.cluster.embedded.state import (
    ManagedClusterMissingError,
    claim_port,
    create_cluster_state,
    managed_catalog_url,
    read_cluster_state,
    state_path,
)
from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import connect


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
    state = create_cluster_state(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", state.port))
        holder.listen()

        moved = claim_port(tmp_path, state)

    assert moved.port != state.port
    assert read_cluster_state(tmp_path) == moved
