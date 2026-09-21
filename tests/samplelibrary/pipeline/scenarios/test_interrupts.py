from __future__ import annotations

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome
from tests.samplelibrary.pipeline.scenarios.harness.plans import GateMoment, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, after, scripted

GATED = StepFault(gate=GateMoment.BEFORE_OUTPUT)
INTERRUPTED_AT_NOTES = BUILT.stopped_at(
    "notes", AttemptOutcome.INTERRUPTED, ExitStatus.INTERRUPTED, after=after("notes")
)


def test_an_interrupt_reaches_the_running_step_once_and_stops_the_run(runner: ScenarioRunner) -> None:
    """Ctrl+C lets the step end as it chooses, then ends the run there; a relaunch takes up the step."""
    host = runner.start(Run(targets=CATALOG, faults=scripted(notes=GATED)))
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)

    host.interrupt()

    runner.finish(host, INTERRUPTED_AT_NOTES, story="the interrupted run")
    runner.run(Run(targets=CATALOG, faults=scripted()), BUILT, story="the relaunch")


def test_a_second_interrupt_stops_a_step_that_let_the_first_pass(runner: ScenarioRunner) -> None:
    host = runner.start(
        Run(targets=CATALOG, faults=scripted(notes=StepFault(gate=GateMoment.BEFORE_OUTPUT, ignores_interrupts=True)))
    )
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)

    host.interrupt()
    host.wait_for_output("waiting for the step to end")
    host.interrupt()

    runner.finish(host, INTERRUPTED_AT_NOTES, story="the run interrupted twice")


def test_a_termination_reaches_the_running_step_as_a_termination(runner: ScenarioRunner) -> None:
    """A machine shutting down or a service manager stopping the run ends the step the same way."""
    host = runner.start(
        Run(targets=CATALOG, faults=scripted(notes=StepFault(gate=GateMoment.BEFORE_OUTPUT, ignores_interrupts=True)))
    )
    host.wait_at("notes", GateMoment.BEFORE_OUTPUT)

    host.terminate()

    runner.finish(host, INTERRUPTED_AT_NOTES, story="the terminated run")
