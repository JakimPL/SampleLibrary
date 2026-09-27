from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Final

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplelibrary.pipeline import devices
from samplelibrary.pipeline.cli import run_pipeline_command
from samplelibrary.pipeline.devices import CPU_DEVICE
from samplelibrary.pipeline.events import (
    AttemptEnded,
    AttemptStarted,
    EventFile,
    EventSink,
    InputsEvaluated,
    PipelineEvent,
    RedoApplied,
    StepDecided,
    StepSealed,
)
from tests.samplelibrary.pipeline.scenarios.harness.plans import (
    FAULT_PLAN_VARIABLE,
    GATES_VARIABLE,
    LEDGER_VARIABLE,
    HostPlan,
    KillPoint,
)
from tests.samplelibrary.pipeline.scenarios.harness.programs import HybridPrograms

HOST_PROGRAM: Final[str] = "samplelibrary pipeline"


class SelfKill:
    """Ends this process the moment a named event is emitted, which is a run dying at an exact point.

    Nothing unwinds and nothing is flushed on the way out, so what a later run finds is exactly what
    a machine losing power at that moment would have left.
    """

    def __init__(self, point: KillPoint) -> None:
        self._point = point

    def emit(self, event: PipelineEvent) -> None:
        if event.kind != self._point.event:
            return
        if self._point.step is not None and _step_of(event) != self._point.step:
            return
        os.kill(os.getpid(), signal.SIGKILL)


def _step_of(event: PipelineEvent) -> str | None:
    match event:
        case InputsEvaluated() | StepDecided() | AttemptStarted() | AttemptEnded() | StepSealed() | RedoApplied():
            return event.step
        case _:
            return None


def main() -> None:
    """Run the pipeline command through its own composition root, with the scenario's programs and death in place."""
    plan_path = Path(sys.argv[1])
    plan = HostPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    faults = plan_path.with_name("faults.json")
    faults.write_text(plan.faults.model_dump_json(), encoding="utf-8")
    os.environ[CONFIG_PATH_ENVIRONMENT_VARIABLE] = str(plan.config)
    os.environ[FAULT_PLAN_VARIABLE] = str(faults)
    os.environ[LEDGER_VARIABLE] = str(plan.ledger)
    os.environ[GATES_VARIABLE] = str(plan.gates)
    if plan.stands_in:
        # The stand-in programs ignore the device, so the run skips asking torch which one this machine offers.
        devices.available_device = lambda: CPU_DEVICE  # type: ignore[method-assign]
    sinks: list[EventSink] = [EventFile(plan.events)]
    if plan.kill_at is not None:
        sinks.append(SelfKill(plan.kill_at))
    run_pipeline_command(
        list(plan.argv),
        prog=HOST_PROGRAM,
        resolver=HybridPrograms(faults=plan.faults, stands_in=plan.stands_in),
        extra_sinks=sinks,
    )


if __name__ == "__main__":
    main()
