from __future__ import annotations

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import KillPoint
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, FIRST_BUILD, KILLED, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import World

REBUILT = BUILT.ending(reset=AttemptOutcome.COMPLETED)


def test_a_run_from_scratch_empties_the_catalog_and_builds_the_same_one_again(runner: ScenarioRunner) -> None:
    """Every part of a catalog rebuilt from nothing reads as it did, so the rebuild moves nothing."""
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    observation = runner.run(Run(targets=CATALOG, from_scratch=True), REBUILT, story="the run from scratch")

    assert "scratch completed" in observation.kinds


def test_a_run_killed_as_it_began_starting_over_finishes_emptying_on_relaunch(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    runner.run(
        Run(targets=CATALOG, from_scratch=True, kill_at=KillPoint(event="scratch started")),
        Expect(outcome=None, exit_status=KILLED, steps={}),
        story="the run from scratch killed as it began",
    )
    assert world.layout.scratch_intent.is_file()

    observation = runner.run(Run(targets=CATALOG), REBUILT, story="the relaunch, asking for nothing more")
    assert "scratch completed" in observation.kinds
    assert not world.layout.scratch_intent.exists()


def test_a_reset_a_reader_holds_off_leaves_the_catalog_whole_until_a_relaunch_finishes_it(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")
    reader = world.hold_a_table("sample")

    runner.run(
        Run(targets=CATALOG, from_scratch=True),
        Expect(
            outcome=RunOutcome.STOPPED,
            exit_status=ExitStatus.REFUSED,
            steps={},
            outcomes={"reset": AttemptOutcome.REFUSED},
        ),
        story="the run from scratch while the app reads the catalog",
    )

    world.release(reader)
    runner.run(Run(targets=CATALOG), REBUILT, story="the relaunch once the app let go")


def test_a_step_asked_to_build_again_must_build_something_of_its_own(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, redo=("notes",), faults=scripted()),
        Expect.refused_run("notes builds nothing of its own"),
        story="a run redoing a pass",
    )
    runner.run(
        Run(targets=("modules",), redo=("relink",), faults=scripted()),
        Expect.refused_run("relink is outside the targets"),
        story="a run redoing a step outside its targets",
    )
    runner.run(
        Run(targets=CATALOG, from_scratch=True, redo=("notes",), faults=scripted()),
        Expect.refused_run("--redo and --from-scratch"),
        story="a run from scratch redoing a step",
    )
