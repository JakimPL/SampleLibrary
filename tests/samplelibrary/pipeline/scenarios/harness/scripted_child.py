from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplecore.storage.atomic import write_bytes_atomically
from samplelibrary.environment import CONFIG_OPTION, MEMORY_CAP_OPTION, MEMORY_SCOPE_OPTION
from samplelibrary.limits.ceiling import MemoryCeiling
from samplelibrary.limits.probe import memory_scope
from samplelibrary.limits.scope import MemoryScopeUnavailable
from samplelibrary.step_lock import hold_step_lock
from tests.samplelibrary.pipeline.scenarios.harness.observe import ABANDONED_GATE
from tests.samplelibrary.pipeline.scenarios.harness.plans import (
    FAULT_PLAN_VARIABLE,
    GATES_VARIABLE,
    LEDGER_VARIABLE,
    REACHED_SUFFIX,
    RELEASE_SUFFIX,
    FaultPlan,
    GateMoment,
    ScriptedEffect,
    StepFault,
    gate_path,
)
from tests.samplelibrary.pipeline.scenarios.harness.stand_ins import run_stand_in

SCRIPTED_CHILD_MODULE: Final[str] = "tests.samplelibrary.pipeline.scenarios.harness.scripted_child"
GATE_POLL_SECONDS: Final[float] = 0.02
GATE_DEADLINE_SECONDS: Final[float] = 120.0
ALLOCATION_BYTES: Final[int] = 32 * 1024 * 1024


def main() -> None:
    """Stand in for one step's command, doing what the scenario's fault plan says it does.

    The process starts the way the dispatcher starts a command -- under the memory ceiling and the
    step lock its command line and environment name -- so a scripted step is found running, held
    and stopped exactly as a real one is. Every scripted run appends to the scenario's own ledger,
    which is evidence apart from anything the pipeline reports about itself.
    """
    step = sys.argv[1]
    options, command = _global_options(sys.argv[2:])
    os.environ[CONFIG_PATH_ENVIRONMENT_VARIABLE] = str(options.config.resolve())
    _enter_the_memory_scope(options, restart=[sys.executable, "-m", SCRIPTED_CHILD_MODULE, *sys.argv[1:]])
    lock = hold_step_lock()
    plan = FaultPlan.model_validate_json(Path(os.environ[FAULT_PLAN_VARIABLE]).read_text(encoding="utf-8"))
    fault = plan.fault_for(step) or StepFault()
    if fault.ignores_interrupts:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    _append_to_the_ledger(step=step, command=command, memory_cap=options.memory_cap)
    if fault.gate is GateMoment.BEFORE_OUTPUT:
        _wait_at_the_gate(step, GateMoment.BEFORE_OUTPUT)
    status = _carry_out(fault)
    if fault.effect is ScriptedEffect.COMPLETE:
        midway = (lambda: _wait_at_the_gate(step, GateMoment.MIDWAY)) if fault.gate is GateMoment.MIDWAY else None
        run_stand_in(command, midway=midway)
    if fault.gate is GateMoment.AFTER_OUTPUT:
        _wait_at_the_gate(step, GateMoment.AFTER_OUTPUT)
    if lock is not None:
        lock.close()
    sys.exit(status)


def _global_options(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """The options the dispatcher reads before a command's name, and the command's own words after them."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(CONFIG_OPTION, type=Path, required=True)
    parser.add_argument(MEMORY_CAP_OPTION, type=str, required=True)
    parser.add_argument(MEMORY_SCOPE_OPTION, type=str, required=True)
    return parser.parse_known_args(argv)


def _enter_the_memory_scope(options: argparse.Namespace, *, restart: list[str]) -> None:
    ceiling = MemoryCeiling.parse(options.memory_cap)
    if not ceiling.enforced:
        return
    try:
        memory_scope().enter(options.memory_scope, ceiling, restart)
    except MemoryScopeUnavailable:
        sys.exit(ExitStatus.REFUSED)


def _carry_out(fault: StepFault) -> int:
    match fault.effect:
        case ScriptedEffect.COMPLETE | ScriptedEffect.NO_OUTPUT:
            return ExitStatus.COMPLETED
        case ScriptedEffect.FAIL:
            return fault.exit_status
        case ScriptedEffect.REFUSE:
            return ExitStatus.REFUSED
        case ScriptedEffect.EXCEED_MEMORY:
            return _exceed_memory()


def _exceed_memory() -> int:
    """Hold ever more memory until the ceiling stops this process, the way a run outgrowing it ends."""
    held: list[bytearray] = []
    try:
        while True:
            held.append(bytearray(b"\x01" * ALLOCATION_BYTES))
    except MemoryError:
        return ExitStatus.MEMORY_CAP_REACHED


def _append_to_the_ledger(*, step: str, command: list[str], memory_cap: str) -> None:
    ledger = Path(os.environ[LEDGER_VARIABLE])
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "step": step,
        "command": command,
        "memory_cap": memory_cap,
        "pid": os.getpid(),
        "at": datetime.now(UTC).isoformat(),
    }
    with ledger.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")
        file.flush()


def _wait_at_the_gate(step: str, moment: GateMoment) -> None:
    """Say the step has reached its gate, then wait there until the scenario lets it go."""
    gate = gate_path(Path(os.environ[GATES_VARIABLE]), step, moment)
    gate.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomically(gate.with_name(gate.name + REACHED_SUFFIX), str(os.getpid()).encode("utf-8"))
    release = gate.with_name(gate.name + RELEASE_SUFFIX)
    deadline = time.monotonic() + GATE_DEADLINE_SECONDS
    while not release.exists():
        if time.monotonic() > deadline:
            _append_to_the_ledger(step=step, command=[ABANDONED_GATE], memory_cap="")
            sys.exit(ExitStatus.FAILED)
        time.sleep(GATE_POLL_SECONDS)


if __name__ == "__main__":
    main()
