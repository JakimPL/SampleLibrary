from __future__ import annotations

import logging
from dataclasses import dataclass

from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.decisions import decide
from samplelibrary.pipeline.execution import read_attempts
from samplelibrary.pipeline.graph import StepGraph
from samplelibrary.pipeline.layout import ATTEMPTS_FILE_NAME, PipelineLayout
from samplelibrary.pipeline.results import StepAction
from samplelibrary.pipeline.steps.kinds import PassStep, Step

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepStatus:
    """What a step would do if a run took it now, and why."""

    step: str
    action: StepAction
    reasons: frozenset[str]
    waits_on: frozenset[str]
    reason: str = ""

    def described(self) -> str:
        """One line a person reads, naming what the step would do and what settles it."""
        if self.waits_on:
            return f"runs after {', '.join(sorted(self.waits_on))}"
        match self.action:
            case StepAction.SKIP:
                return "satisfied"
            case StepAction.SEAL:
                return "seals what an earlier run built"
            case StepAction.REFUSE:
                return f"refuses: {self.reason}"
            case StepAction.RUN:
                return f"runs because {', '.join(sorted(self.reasons))}" if self.reasons else "runs"


def read_status(context: PipelineContext, graph: StepGraph, targets: tuple[str, ...]) -> tuple[StepStatus, ...]:
    """What each step of the named targets would do now, read without running anything.

    A step whose inputs an earlier step would change reads as waiting on it, since what it would do
    is settled by what that step leaves behind. A pass reads as leaving the catalog as it stands, which
    it does over a collection that stands still.
    """
    statuses: list[StepStatus] = []
    unsettled: set[str] = set()
    for step in graph.order(targets):
        waits_on = frozenset(set(step.requires) & unsettled)
        status = _status_of(context, step, waits_on)
        if status.action is not StepAction.SKIP and not isinstance(step, PassStep):
            unsettled.add(step.name)
        statuses.append(status)
    return tuple(statuses)


def report_status(statuses: tuple[StepStatus, ...]) -> None:
    """Say what every step would do, one line each."""
    for status in statuses:
        _logger.info("%-22s %s", status.step, status.described())


def report_last_attempts(layout: PipelineLayout) -> None:
    """Name how each step ended the last time a run of this library tried it."""
    latest = {}
    for run in sorted(layout.runs.glob("*")):
        for attempt in read_attempts(run / ATTEMPTS_FILE_NAME):
            latest[attempt.step] = attempt
    for step, attempt in sorted(latest.items()):
        _logger.info("%-22s last %s (%s)", step, attempt.outcome.value, attempt.log)


def _status_of(context: PipelineContext, step: Step, waits_on: frozenset[str]) -> StepStatus:
    if waits_on:
        return StepStatus(step=step.name, action=StepAction.RUN, reasons=frozenset(), waits_on=waits_on)
    plan = decide(context, step)
    return StepStatus(
        step=step.name, action=plan.action, reasons=plan.reasons, waits_on=frozenset(), reason=plan.reason
    )
