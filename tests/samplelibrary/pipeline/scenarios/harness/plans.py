from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from samplecore.models.base import FROZEN

# Neither begins with SAMPLELIBRARY_, which a pipeline clears from every step's environment.
FAULT_PLAN_VARIABLE: Final[str] = "SCENARIO_FAULTS"
LEDGER_VARIABLE: Final[str] = "SCENARIO_LEDGER"
GATES_VARIABLE: Final[str] = "SCENARIO_GATES"
REACHED_SUFFIX: Final[str] = ".reached"
RELEASE_SUFFIX: Final[str] = ".release"


@unique
class ScriptedEffect(StrEnum):
    """What a scripted step does in place of the command it stands for."""

    COMPLETE = "complete"
    FAIL = "fail"
    REFUSE = "refuse"
    NO_OUTPUT = "no output"
    EXCEED_MEMORY = "exceed memory"


@unique
class GateMoment(StrEnum):
    """Where a scripted step stops and waits for the scenario: before its output, partway through it, or after.

    Partway means once the first checkpoint of a stood-in command is committed.
    """

    BEFORE_OUTPUT = "before output"
    MIDWAY = "midway"
    AFTER_OUTPUT = "after output"


class StepFault(BaseModel):
    """What one scripted step does, and the moment it waits at for the scenario to act."""

    model_config = FROZEN

    effect: ScriptedEffect = ScriptedEffect.COMPLETE
    exit_status: int = 1
    gate: GateMoment | None = None
    ignores_interrupts: bool = False
    varies: bool = False


class FaultPlan(BaseModel):
    """Which steps a scenario scripts, and what each of them does; every other step runs its real command."""

    model_config = FROZEN

    steps: Mapping[str, StepFault] = {}

    def fault_for(self, step: str) -> StepFault | None:
        return self.steps.get(step)


class KillPoint(BaseModel):
    """The event a run's own process dies at, with the step it names where one is named."""

    model_config = FROZEN

    event: str
    step: str | None = None


class HostPlan(BaseModel):
    """One pipeline command a scenario runs: its words, the steps it scripts, and where it dies if it does."""

    model_config = FROZEN

    config: Path
    argv: tuple[str, ...]
    faults: FaultPlan
    ledger: Path
    gates: Path
    events: Path
    kill_at: KillPoint | None = None


def gate_path(gates: Path, step: str, moment: GateMoment) -> Path:
    """The path a step's gate at one moment is known by, which both sides of the gate agree on."""
    return gates / f"{step}.{moment.name.lower()}"
