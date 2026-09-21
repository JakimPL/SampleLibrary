from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final

from samplelibrary.pipeline.results import AttemptOutcome
from tests.samplelibrary.pipeline.scenarios.harness.observe import RunObservation, log_tail

if TYPE_CHECKING:
    from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect

LOG_TAIL_LINES: Final[int] = 12
ABSENT: Final[str] = "-"


def render_divergence(story: str, problems: list[str], observation: RunObservation, expect: Expect) -> str:
    """The story of where a run left its scenario: each step expected beside observed, and the logs of what failed."""
    steps = list(dict.fromkeys([*expect.steps, *observation.verdicts]))
    width = max((len(step) for step in steps), default=4)
    lines = [f"{story} diverged:", *(f"  - {problem}" for problem in problems), ""]
    lines.append(f"  {'step':<{width}}  {'expected':<12}  {'observed':<12}  attempt")
    for step in steps:
        expected = expect.steps.get(step)
        observed = observation.verdicts.get(step)
        marker = " " if expected == observed else "!"
        attempt = observation.outcomes.get(step)
        lines.append(f"{marker} {step:<{width}}  {_named(expected):<12}  {_named(observed):<12}  {_named(attempt)}")
    lines.append(f"  exit status {observation.exit_status}, run {_named(observation.outcome)}")
    if observation.refusal:
        lines.append(f"  refusal: {observation.refusal}")
    for step, outcome in observation.outcomes.items():
        if outcome is not AttemptOutcome.COMPLETED:
            lines.extend(
                ["", f"  the last lines of {step}'s log:", log_tail(observation.directory, step, LOG_TAIL_LINES)]
            )
    return "\n".join(lines)


def _named(value: StrEnum | None) -> str:
    return ABSENT if value is None else value.value
