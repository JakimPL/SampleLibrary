from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

from samplelibrary.environment import PACKAGE_NAME
from samplelibrary.pipeline.steps.cloud import CLOUD
from samplelibrary.pipeline.steps.descriptor import (
    COMPLETION,
    DESCRIPTOR,
    EMBEDDING,
    EVALUATION,
    GRID_CACHE,
    MODULE_EVALUATION,
)
from samplelibrary.pipeline.steps.listening import CATEGORIES, HEARING_TEACHER, TEACHER
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan
from tests.samplelibrary.pipeline.scenarios.harness.scripted_child import SCRIPTED_CHILD_MODULE

STOOD_IN_STEPS: Final[frozenset[str]] = frozenset(
    {
        TEACHER,
        HEARING_TEACHER,
        CATEGORIES,
        GRID_CACHE,
        DESCRIPTOR,
        EMBEDDING,
        COMPLETION,
        EVALUATION,
        MODULE_EVALUATION,
        CLOUD,
    }
)


@dataclass(frozen=True)
class HybridPrograms:  # pylint: disable=unused-argument
    """Runs every step as the real command, except the ones a scenario scripts and the ones reading a model.

    A step reading a listening model or training a network runs its command with the model stood in
    for, so a scenario runs in seconds on any machine; with `stands_in` off, every step runs the
    real program.

    A scripted step still takes the very command line the step builds, so the flags a step passes
    are exercised whatever the program behind them does.
    """

    faults: FaultPlan
    stands_in: bool

    def program(self, step: str, command: tuple[str, ...]) -> list[str]:
        if self.faults.fault_for(step) is None and not (self.stands_in and step in STOOD_IN_STEPS):
            return [sys.executable, "-m", PACKAGE_NAME]
        return [sys.executable, "-m", SCRIPTED_CHILD_MODULE, step]
