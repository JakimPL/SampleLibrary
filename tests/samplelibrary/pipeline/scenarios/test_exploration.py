from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from hypothesis import HealthCheck, settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule, run_state_machine_as_test
from hypothesis.strategies import sampled_from
from sqlalchemy import Connection

from samplecore.storage.curation import curation_metadata
from samplecore.storage.database import metadata
from samplelibrary.pipeline.results import RunOutcome
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan, GateMoment, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner, wait_until_released
from tests.samplelibrary.pipeline.scenarios.harness.world import World, WorldSetup

TARGETS: Final[tuple[str, ...]] = ("catalog", "teacher", "suggestions")
LABELS: Final[tuple[str, ...]] = ("SNARE", "BASS DRUM", "PAD: WARM")
MAXIMUM_ADDED_FILES: Final[int] = 2
MAXIMUM_ADDED_MODULES: Final[int] = 2
EXAMPLES: Final[int] = 6
ACTS_PER_EXAMPLE: Final[int] = 8
ORPHAN_DEADLINE_SECONDS: Final[float] = 60.0

pytestmark = pytest.mark.pipeline_explore


class LibraryStory(RuleBasedStateMachine):
    """A library acted on in whatever order Hypothesis draws: files and modules arrive and change, labels are
    written, runs go to their end or are interrupted partway.

    Nothing states what a run should do; every run is held to the oracles alone -- the evidence it
    left, what `status` said before it, a status reading every step settled once it completes, and
    no lock outliving it. A divergence shrinks to the shortest sequence of acts that shows it.
    """

    examples: int = 0

    def __init__(self, root: Path, database_url: str, connection: Connection) -> None:
        super().__init__()
        _empty_the_catalog(connection)
        LibraryStory.examples += 1
        self.world = World(
            root=root / f"example-{LibraryStory.examples:02d}",
            database_url=database_url,
            connection=connection,
            setup=WorldSetup(),
        )
        self.world.build()
        self.runner = ScenarioRunner(world=self.world)
        self.cataloged = False
        self.acts = 0

    def _story(self, act: str) -> str:
        self.acts += 1
        return f"act {self.acts}: {act}"

    @precondition(lambda self: self.world.added_pack_files < MAXIMUM_ADDED_FILES)
    @rule()
    def add_a_sample_file(self) -> None:
        self.world.add_pack_file()

    @precondition(lambda self: self.world.added_modules < MAXIMUM_ADDED_MODULES)
    @rule()
    def add_a_module(self) -> None:
        self.world.add_module()

    @rule()
    def touch_a_sample_file(self) -> None:
        self.world.touch_pack_file()

    @precondition(lambda self: len(self.world.pack_files()) > 1)
    @rule()
    def delete_a_sample_file(self) -> None:
        self.world.delete_pack_file()

    @precondition(lambda self: self.cataloged)
    @rule(label=sampled_from(LABELS))
    def label_a_sample(self, label: str) -> None:
        self.world.label_a_sample(label)

    @rule()
    def run_to_the_end(self) -> None:
        observation = self.runner.explore(self.runner.start(Run(targets=TARGETS)), story=self._story("a run"))
        assert observation.outcome is RunOutcome.COMPLETED, f"act {self.acts}: the run ended {observation.outcome}"
        self.cataloged = True

    @rule()
    def interrupt_a_reading_partway(self) -> None:
        host = self.runner.start(
            Run(targets=TARGETS, faults=FaultPlan(steps={"teacher": StepFault(gate=GateMoment.MIDWAY)}))
        )
        if host.reaches("teacher", GateMoment.MIDWAY):
            host.interrupt()
        observation = self.runner.explore(host, story=self._story("a run interrupted while the teacher reads"))
        assert observation.outcome in (RunOutcome.COMPLETED, RunOutcome.STOPPED)
        wait_until_released(self.world, ORPHAN_DEADLINE_SECONDS)
        self.cataloged = True

    @invariant()
    def holds_no_lock_between_acts(self) -> None:
        assert not self.world.stray_locks(), f"after act {self.acts}: {self.world.stray_locks()} still held"

    def teardown(self) -> None:
        self.runner.close()
        self.world.close()


def _empty_the_catalog(connection: Connection) -> None:
    """Start an example from an empty catalog, the way every scenario's own database starts."""
    connection.rollback()
    for table in [*reversed(metadata.sorted_tables), *reversed(curation_metadata.sorted_tables)]:
        connection.execute(table.delete())
    connection.commit()


def test_a_library_acted_on_in_any_order_keeps_every_oracle(
    tmp_path: Path, _database_url: str, connection: Connection
) -> None:
    run_state_machine_as_test(
        lambda: LibraryStory(tmp_path, _database_url, connection),
        settings=settings(
            max_examples=EXAMPLES,
            stateful_step_count=ACTS_PER_EXAMPLE,
            deadline=None,
            database=None,
            suppress_health_check=[HealthCheck.too_slow],
        ),
    )
