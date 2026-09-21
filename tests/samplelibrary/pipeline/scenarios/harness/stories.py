from __future__ import annotations

import signal
from typing import Final

from samplelibrary.pipeline.results import StepVerdict
from samplelibrary.pipeline.steps.library import CATALOG_STEPS
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan, StepFault

CATALOG: Final[tuple[str, ...]] = ("catalog",)
CATALOG_PASSES: Final[tuple[str, ...]] = tuple(step for step in CATALOG_STEPS if step != "labels")
BUILT: Final[Expect] = Expect.completed(CATALOG_STEPS, StepVerdict.RAN).with_steps(labels=StepVerdict.SATISFIED)
FIRST_BUILD: Final[Expect] = BUILT.moving("modules", "samples", "relations", "files", "passes")
KILLED: Final[int] = -signal.SIGKILL


def after(step: str) -> tuple[str, ...]:
    """The catalog's steps a run takes after this one."""
    return CATALOG_STEPS[CATALOG_STEPS.index(step) + 1 :]


def scripted(**faults: StepFault) -> FaultPlan:
    """Every catalog pass scripted to complete at once, apart from the faults named here.

    A scenario about how the pipeline treats its steps reads the same over scripted passes, and runs
    in a fraction of the time the real passes take.
    """
    named = {name.replace("_", "-"): fault for name, fault in faults.items()}
    return FaultPlan(steps={step: named.get(step, StepFault()) for step in CATALOG_PASSES})


def killed_during(step: str) -> Expect:
    """A catalog run whose own process died while this step was under way, having decided every step before it."""
    reached = CATALOG_STEPS[: CATALOG_STEPS.index(step) + 1]
    return Expect(
        outcome=None,
        exit_status=KILLED,
        steps={name: BUILT.steps[name] for name in reached},
    )
