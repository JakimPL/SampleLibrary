from __future__ import annotations

import sys
from dataclasses import dataclass

from samplelibrary.environment import PACKAGE_NAME
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan
from tests.samplelibrary.pipeline.scenarios.harness.scripted_child import SCRIPTED_CHILD_MODULE


@dataclass(frozen=True)
class HybridPrograms:  # pylint: disable=unused-argument
    """Runs every step as the real command, except the ones a scenario scripts.

    A scripted step still takes the very command line the step builds, so the flags a step passes
    are exercised whatever the program behind them does.
    """

    faults: FaultPlan

    def program(self, step: str, command: tuple[str, ...]) -> list[str]:
        if self.faults.fault_for(step) is None:
            return [sys.executable, "-m", PACKAGE_NAME]
        return [sys.executable, "-m", SCRIPTED_CHILD_MODULE, step]
