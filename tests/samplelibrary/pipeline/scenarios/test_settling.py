from __future__ import annotations

from samplelibrary.pipeline.results import StepVerdict
from samplelibrary.pipeline.steps.library import CATALOG_STEPS
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.observe import ledger_commands
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.world import World

CATALOG = ("catalog",)
BUILT = Expect.completed(CATALOG_STEPS, StepVerdict.RAN).with_steps(labels=StepVerdict.SATISFIED)
FIRST_BUILD = BUILT.moving("modules", "samples", "relations", "files", "passes")


def test_a_library_is_built_once_and_then_stands(runner: ScenarioRunner) -> None:
    """The first run builds the catalog; a second finds every pass with nothing left to do."""
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    runner.run(Run(targets=CATALOG), BUILT, story="the run after it")


def test_a_module_added_to_the_collection_reaches_the_catalog(runner: ScenarioRunner, world: World) -> None:
    """A module with no relative among the others brings its samples and moves no relation."""
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    world.add_module()

    runner.run(
        Run(targets=CATALOG), BUILT.moving("modules", "samples", "passes"), story="the run after a module arrived"
    )
    runner.run(Run(targets=CATALOG), BUILT, story="the run after that")


def test_a_sample_file_added_to_the_pack_reaches_the_catalog(runner: ScenarioRunner, world: World) -> None:
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    world.add_pack_file()

    runner.run(
        Run(targets=CATALOG), BUILT.moving("samples", "files", "passes"), story="the run after a sample file arrived"
    )


def test_a_file_whose_write_time_moved_alone_leaves_the_catalog_as_it_was(runner: ScenarioRunner, world: World) -> None:
    """Its bytes decide what it is, so a rescan reads it again and finds the sample it already holds."""
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")

    world.touch_pack_file()

    runner.run(Run(targets=CATALOG), BUILT, story="the run after a touch")


def test_a_run_naming_one_step_takes_it_and_what_it_needs(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=("modules",)),
        Expect.completed(("labels", "modules"), StepVerdict.RAN)
        .with_steps(labels=StepVerdict.SATISFIED)
        .moving("modules", "samples", "passes"),
        story="a run of the modules step alone",
    )


def test_every_step_is_handed_the_command_line_it_builds(runner: ScenarioRunner) -> None:
    """A scripted step still takes the words the step builds, so the command line itself is exercised.

    With the collection passes scripted the catalog stays empty, and the passes after them record
    that they finished over it.
    """
    scripted = FaultPlan(steps={"modules": StepFault(), "sample-files": StepFault()})

    host = runner.start(Run(targets=CATALOG, faults=scripted))
    runner.finish(host, BUILT.moving("passes"), story="a run whose collection passes are scripted")

    commands = ledger_commands(host.ledger)
    assert commands["modules"] == ("extract", "--prune", "--workers", "1")
    assert commands["sample-files"] == ("files", "--prune", "--workers", "1")
