from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from samplelibrary.pipeline.artifacts import write_step_record
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.events import (
    AttemptEnded,
    AttemptStarted,
    InputsEvaluated,
    LockLost,
    RedoApplied,
    RunEnded,
    RunRefused,
    RunStarted,
    Sinks,
    StepDecided,
    StepSealed,
)
from samplelibrary.pipeline.execution import Attempt, record_attempt, run_step_command
from samplelibrary.pipeline.graph import StepGraph
from samplelibrary.pipeline.locks import PipelineLock, step_is_running
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepAction, StepPlan, StepVerdict
from samplelibrary.pipeline.steps.kinds import FileArtifactStep, MissingOutput, Step

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRequest:
    """What one run was asked for: which targets, whether it starts over, and what it builds again."""

    targets: tuple[str, ...] = ()
    redo: tuple[str, ...] = ()
    follow: bool = False


@dataclass(frozen=True)
class RunReport:
    """What one run decided about every step it reached, and how it ended."""

    outcome: RunOutcome
    verdicts: Mapping[str, StepVerdict]
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)
    refusal: str = ""

    @property
    def settled(self) -> bool:
        """Whether every step the run reached is done, which is what a finished run leaves."""
        return self.outcome is RunOutcome.COMPLETED


def run_pipeline(
    context: PipelineContext, graph: StepGraph, request: RunRequest, sinks: Sinks, lock: PipelineLock
) -> RunReport:
    """Take every step of the named targets in order, running the ones with work left.

    A step decides for itself whether it is done, from the outputs it stands for rather than from
    anything this run remembers. The first step that fails, refuses or is interrupted ends the run,
    and the steps that needed it are recorded as unreached, so a relaunch takes up exactly there.
    Every durable effect is made before the event reporting it, so a run that dies at any moment
    leaves a library a later run reads correctly.
    """
    steps = graph.order(request.targets)
    sinks.emit(
        RunStarted(
            run_id=context.run.run_id,
            targets=request.targets or ("all",),
            steps=tuple(step.name for step in steps),
        )
    )
    running = _steps_already_running(context, steps)
    if running:
        return _refused(sinks, f"{', '.join(running)} is still running from an earlier run of this library")

    _apply_redo(context, graph, request, sinks)
    verdicts: dict[str, StepVerdict] = {}
    attempts: list[Attempt] = []
    blocked: set[str] = set()
    for step in steps:
        if set(step.requires) & blocked:
            verdicts[step.name] = StepVerdict.NOT_REACHED
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.NOT_REACHED, reasons=()))
            continue
        if not lock.held():
            sinks.emit(LockLost())
            sinks.emit(RunEnded(outcome=RunOutcome.LOCK_LOST))
            return RunReport(outcome=RunOutcome.LOCK_LOST, verdicts=verdicts, attempts=tuple(attempts))

        verdict, attempt = _take(context, step, sinks, request=request)
        verdicts[step.name] = verdict
        if attempt is not None:
            attempts.append(attempt)
        if verdict in (StepVerdict.RAN, StepVerdict.RESEALED, StepVerdict.SATISFIED):
            continue
        blocked.add(step.name)
        blocked.update(graph.descendants(step.name))
        for name in (name for name in (later.name for later in steps) if name in blocked and name not in verdicts):
            verdicts[name] = StepVerdict.NOT_REACHED
        sinks.emit(RunEnded(outcome=RunOutcome.STOPPED))
        return RunReport(outcome=RunOutcome.STOPPED, verdicts=verdicts, attempts=tuple(attempts))

    sinks.emit(RunEnded(outcome=RunOutcome.COMPLETED))
    return RunReport(outcome=RunOutcome.COMPLETED, verdicts=verdicts, attempts=tuple(attempts))


def _take(
    context: PipelineContext, step: Step, sinks: Sinks, *, request: RunRequest
) -> tuple[StepVerdict, Attempt | None]:
    """Decide one step and carry out whatever it says is left, reporting how it went."""
    plan = step.evaluate(context)
    sinks.emit(InputsEvaluated(step=step.name, inputs=dict(plan.inputs), digest=plan.digest))
    match plan.action:
        case StepAction.SKIP:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.SATISFIED, reasons=()))
            return StepVerdict.SATISFIED, None
        case StepAction.REFUSE:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.REFUSED, reasons=()))
            sinks.emit(RunRefused(reason=f"{step.name}: {plan.reason}"))
            return StepVerdict.REFUSED, None
        case StepAction.SEAL:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.RESEALED, reasons=tuple(sorted(plan.reasons))))
            return (StepVerdict.RESEALED, None) if _sealed(context, step, plan, sinks) else (StepVerdict.REFUSED, None)
        case StepAction.RUN:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.RAN, reasons=tuple(sorted(plan.reasons))))
            return _run(context, step, plan, sinks, request=request)


def _run(
    context: PipelineContext, step: Step, plan: StepPlan, sinks: Sinks, *, request: RunRequest
) -> tuple[StepVerdict, Attempt]:
    """Run one step's command, then bind what it produced to the inputs it was built from."""
    scope_name = context.scope_name(step.name)
    log = context.run.log(step.name)
    sinks.emit(AttemptStarted(step=step.name, argv=plan.argv, log=str(log), scope=scope_name))
    attempt = run_step_command(context, step=step.name, command=plan.argv, follow=request.follow)
    if attempt.completed and not _sealed(context, step, plan, sinks):
        attempt = _without_output(attempt)
    record_attempt(context.run.attempts, attempt)
    sinks.emit(AttemptEnded(step=step.name, outcome=attempt.outcome, exit_status=attempt.exit_status))
    return (StepVerdict.RAN if attempt.completed else StepVerdict.REFUSED), attempt


def _sealed(context: PipelineContext, step: Step, plan: StepPlan, sinks: Sinks) -> bool:
    """Bind a step's output to its inputs, reporting whether the output was there to bind."""
    try:
        outputs = step.seal(context, plan)
    except MissingOutput as error:
        _logger.error("%s", error)
        return False
    write_step_record(context.layout.step_record(step.name), inputs=plan.inputs, outputs=outputs)
    sinks.emit(StepSealed(step=step.name, outputs=dict(outputs)))
    return True


def _without_output(attempt: Attempt) -> Attempt:
    """The same attempt, read as one that ended a success and left nothing behind."""
    return Attempt(
        step=attempt.step,
        argv=attempt.argv,
        outcome=AttemptOutcome.NO_OUTPUT,
        exit_status=attempt.exit_status,
        log=attempt.log,
        started_at=attempt.started_at,
        ended_at=datetime.now(UTC),
    )


def _apply_redo(context: PipelineContext, graph: StepGraph, request: RunRequest, sinks: Sinks) -> None:
    """Drop what the named steps built, so this run builds it again."""
    for name in request.redo:
        step = graph.step(name)
        match step:
            case FileArtifactStep():
                step.forget(context)
                sinks.emit(RedoApplied(step=name))
            case _:
                raise RedoRefused(
                    f"{name} builds nothing of its own to drop; --redo names a step that builds a file or a directory"
                )


def _steps_already_running(context: PipelineContext, steps: Sequence[Step]) -> tuple[str, ...]:
    """The steps of this library another process still holds, which a run leaves alone."""
    return tuple(step.name for step in steps if step_is_running(context.connection, context.scope_name(step.name)))


def _refused(sinks: Sinks, reason: str) -> RunReport:
    sinks.emit(RunRefused(reason=reason))
    sinks.emit(RunEnded(outcome=RunOutcome.REFUSED))
    return RunReport(outcome=RunOutcome.REFUSED, verdicts={}, refusal=reason)


class RedoRefused(ValueError):
    """Raised when a run is asked to build again what a step does not build for itself."""
