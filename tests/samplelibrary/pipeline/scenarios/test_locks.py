from __future__ import annotations

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict
from samplelibrary.pipeline.scheduler import LOCK_HELD_REFUSAL
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import GateMoment, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, after, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import World

GATED_NOTES = scripted(notes=StepFault(gate=GateMoment.BEFORE_OUTPUT))


def test_a_run_is_refused_while_another_holds_the_library(runner: ScenarioRunner, world: World) -> None:
    held = world.hold_the_pipeline_lock()

    runner.run(Run(targets=CATALOG, faults=scripted()), Expect.refused_run(LOCK_HELD_REFUSAL), story="the second run")

    world.release(held)
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the run once the first let go")


def test_a_run_is_refused_while_a_step_of_an_earlier_run_still_holds_its_lock(
    runner: ScenarioRunner, world: World
) -> None:
    """A step running under no ceiling is found by its lock alone."""
    held = world.hold_a_step_lock("equivalence")

    runner.run(
        Run(targets=CATALOG, faults=scripted()),
        Expect.refused_run("equivalence is still running"),
        story="the run while equivalence still runs",
    )

    world.release(held)
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the run once equivalence ended")


def test_two_runs_of_one_library_take_turns(runner: ScenarioRunner) -> None:
    first = runner.start(Run(targets=CATALOG, faults=GATED_NOTES))
    first.wait_at("notes", GateMoment.BEFORE_OUTPUT)

    runner.run(
        Run(targets=CATALOG, faults=scripted()),
        Expect.refused_run(LOCK_HELD_REFUSAL),
        story="the run started beside it",
        still_running=("pipeline", "notes"),
    )

    first.release("notes", GateMoment.BEFORE_OUTPUT)
    runner.finish(first, BUILT, story="the first run")


def test_a_run_that_lost_its_lock_lets_its_step_finish_and_starts_nothing_more(
    runner: ScenarioRunner, world: World
) -> None:
    host = runner.start(Run(targets=CATALOG, faults=GATED_NOTES))
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)

    world.end_the_pipeline_lock_session()
    host.release("notes", GateMoment.BEFORE_OUTPUT)

    runner.finish(
        host,
        Expect(
            outcome=RunOutcome.LOCK_LOST,
            exit_status=ExitStatus.FAILED,
            steps={
                **{name: verdict for name, verdict in BUILT.steps.items() if name not in after("notes")},
                **{name: StepVerdict.NOT_REACHED for name in after("notes")},
            },
            outcomes={"notes": AttemptOutcome.COMPLETED},
        ),
        story="the run whose lock went",
    )
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")
