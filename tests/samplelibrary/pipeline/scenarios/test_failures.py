from __future__ import annotations

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.execution import read_attempts
from samplelibrary.pipeline.layout import ATTEMPTS_FILE_NAME
from samplelibrary.pipeline.results import AttemptOutcome
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import GateMoment, ScriptedEffect, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, after, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import World

UNREADABLE = Expect(outcome=None, exit_status=ExitStatus.REFUSED, steps={})


def _failing(exit_status: int) -> StepFault:
    return StepFault(effect=ScriptedEffect.FAIL, exit_status=exit_status)


def test_a_failing_step_stops_the_run_and_a_relaunch_takes_it_up(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(notes=_failing(ExitStatus.FAILED))),
        BUILT.stopped_at("notes", AttemptOutcome.FAILED, ExitStatus.FAILED, after=after("notes")),
        story="a run whose notes fail",
    )

    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_step_refusing_its_work_ends_the_run_as_refused(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(equivalence=StepFault(effect=ScriptedEffect.REFUSE))),
        BUILT.stopped_at("equivalence", AttemptOutcome.REFUSED, ExitStatus.REFUSED, after=after("equivalence")),
        story="a run whose equivalence pass refuses",
    )


def test_a_step_that_outgrew_its_ceiling_ends_the_run_as_one(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(thumbnails=_failing(ExitStatus.MEMORY_CAP_REACHED))),
        BUILT.stopped_at(
            "thumbnails", AttemptOutcome.MEMORY_CAP_REACHED, ExitStatus.MEMORY_CAP_REACHED, after=after("thumbnails")
        ),
        story="a run whose thumbnails outgrow their ceiling",
    )


def test_a_step_killed_outright_under_no_ceiling_is_a_failure(runner: ScenarioRunner) -> None:
    """Only a ceiling explains a kill, so without one a killed step is a step that broke."""
    runner.run(
        Run(targets=CATALOG, faults=scripted(notes=_failing(137))),
        BUILT.stopped_at("notes", AttemptOutcome.FAILED, ExitStatus.FAILED, after=after("notes")),
        story="a run whose notes are killed",
    )


def test_a_step_ending_as_a_shell_ends_an_interrupted_process_is_interrupted(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=CATALOG, faults=scripted(relink=_failing(ExitStatus.INTERRUPTED))),
        BUILT.stopped_at("relink", AttemptOutcome.INTERRUPTED, ExitStatus.INTERRUPTED, after=()),
        story="a run whose relink ends interrupted",
    )


def test_a_torn_attempt_record_leaves_every_whole_attempt_readable(runner: ScenarioRunner) -> None:
    """A run killed while appending leaves half a line, which every reader of the record steps over."""
    observation = runner.run(
        Run(targets=CATALOG, faults=scripted(thumbnails=_failing(ExitStatus.FAILED))),
        BUILT.stopped_at("thumbnails", AttemptOutcome.FAILED, ExitStatus.FAILED, after=after("thumbnails")),
        story="a run whose thumbnails fail",
    )
    assert observation.directory is not None
    record = observation.directory / ATTEMPTS_FILE_NAME
    with record.open("a", encoding="utf-8") as file:
        file.write('{"step": "equivalence", "argv": [')

    assert [attempt.step for attempt in read_attempts(record)] == ["modules", "sample-files", "notes", "thumbnails"]
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_pipeline_table_holding_an_unknown_setting_refuses_the_run(runner: ScenarioRunner, world: World) -> None:
    world.set_pipeline_table('memory_cap = "none"\nworkers = 1\nparallel = true\n')

    runner.run(Run(targets=CATALOG), UNREADABLE, story="a run over a table naming an unknown setting")

    assert not world.layout.runs.exists()


def test_a_table_for_a_step_the_pipeline_does_not_hold_refuses_the_run(runner: ScenarioRunner, world: World) -> None:
    world.set_pipeline_table('memory_cap = "none"\n\n[pipeline.thumbnail]\nmemory_cap = "2G"\n')

    runner.run(Run(targets=CATALOG), UNREADABLE, story="a run over a table for a misspelled step")


def test_a_ceiling_written_another_way_refuses_the_run(runner: ScenarioRunner, world: World) -> None:
    world.set_pipeline_table('memory_cap = "plenty"\n')

    runner.run(Run(targets=CATALOG), UNREADABLE, story="a run over an unreadable ceiling")


def test_a_configuration_broken_while_a_run_goes_on_reaches_only_the_next_run(
    runner: ScenarioRunner, world: World
) -> None:
    """Every step of a run reads the configuration the run started with."""
    host = runner.start(Run(targets=CATALOG, faults=scripted(notes=StepFault(gate=GateMoment.BEFORE_OUTPUT))))
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)
    world.set_pipeline_table('memory_cap = "plenty"\n')
    host.release("notes", GateMoment.BEFORE_OUTPUT)

    runner.finish(host, BUILT, story="the run the configuration broke under", settles=False)
    runner.run(Run(targets=CATALOG), UNREADABLE, story="the run after it")
