from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection

from tests.paths import PIPELINE_SCENARIOS_DIRECTORY
from tests.samplelibrary.pipeline.scenarios.harness.runner import ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.slots import claim_scenario_slot
from tests.samplelibrary.pipeline.scenarios.harness.world import World, WorldSetup


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every scenario, which `just test` leaves to `just test-all` for the minutes they take together."""
    for item in items:
        if PIPELINE_SCENARIOS_DIRECTORY in item.path.parents:
            item.add_marker(pytest.mark.pipeline_scenario)


@pytest.fixture(name="scenario_slot")
def fixture_scenario_slot(_server_url: str) -> Iterator[None]:
    """A slot on the server held for the whole scenario, so worlds on every test worker share its connections."""
    slot = claim_scenario_slot(_server_url)
    yield
    slot.release()


@pytest.fixture(name="world")
def fixture_world(tmp_path: Path, _database_url: str, connection: Connection, scenario_slot: None) -> Iterator[World]:
    """A small library of its own for one scenario: a few modules, a sample pack and a configuration."""
    world = World(root=tmp_path / "world", database_url=_database_url, connection=connection, setup=WorldSetup())
    world.build()
    yield world
    world.close()


@pytest.fixture(name="runner")
def fixture_runner(world: World) -> Iterator[ScenarioRunner]:
    """The scenario's own way of acting on its world and holding every run to what it says."""
    runner = ScenarioRunner(world=world)
    yield runner
    runner.close()
