from __future__ import annotations

from samplelibrary.pipeline.results import StepVerdict
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import GateMoment, KillPoint, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner, wait_until_released
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, KILLED, killed_during, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import World

ORPHAN_DEADLINE_SECONDS = 60.0


def test_a_run_killed_while_its_step_runs_leaves_the_step_to_finish_and_the_relaunch_waits_for_it(
    runner: ScenarioRunner, world: World
) -> None:
    """The step outlives the run that started it, and holds its lock until it ends however long that takes."""
    host = runner.start(Run(targets=CATALOG, faults=scripted(notes=StepFault(gate=GateMoment.BEFORE_OUTPUT))))
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)
    host.kill()
    runner.finish(host, killed_during("notes"), story="the run killed during notes")

    runner.run(
        Run(targets=CATALOG, faults=scripted()),
        Expect.refused_run("notes is still running"),
        story="the relaunch while notes still runs",
        still_running=("notes",),
    )

    host.release("notes", GateMoment.BEFORE_OUTPUT)
    wait_until_released(world, ORPHAN_DEADLINE_SECONDS)
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch after notes ended")


def test_a_run_killed_right_after_a_step_sealed_goes_on_from_there(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(), kill_at=KillPoint(event="step sealed", step="thumbnails")),
        killed_during("thumbnails"),
        story="the run killed once thumbnails sealed",
    )

    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_run_killed_as_it_started_a_step_runs_that_step_on_relaunch(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(), kill_at=KillPoint(event="attempt started", step="equivalence")),
        killed_during("equivalence"),
        story="the run killed as equivalence started",
    )

    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_run_killed_as_it_took_the_library_leaves_it_as_it_was(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(), kill_at=KillPoint(event="lock acquired")),
        Expect(outcome=None, exit_status=KILLED, steps={}),
        story="the run killed as it took the library",
    )

    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_step_killed_after_its_work_is_done_is_satisfied_by_what_it_left(runner: ScenarioRunner) -> None:
    """Labels read in by a step whose run died before recording it stand read on relaunch."""
    host = runner.start(Run(targets=CATALOG, faults=scripted(relink=StepFault(gate=GateMoment.AFTER_OUTPUT))))
    host.wait_at("relink", GateMoment.AFTER_OUTPUT)
    host.kill()
    runner.finish(host, killed_during("relink"), story="the run killed as relink finished")
    host.release("relink", GateMoment.AFTER_OUTPUT)
    wait_until_released(runner.world, ORPHAN_DEADLINE_SECONDS)

    runner.run(
        Run(targets=CATALOG, faults=scripted()),
        BUILT.with_steps(labels=StepVerdict.SATISFIED),
        story="the relaunch",
    )
