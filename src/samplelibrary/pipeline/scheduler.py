from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.artifacts import write_step_record
from samplelibrary.pipeline.context import RunSession
from samplelibrary.pipeline.events import (
    AttemptEnded,
    AttemptStarted,
    InputsEvaluated,
    LockAcquired,
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
from samplelibrary.pipeline.scratch import RESET_STEP, scratch_is_unfinished, start_from_scratch
from samplelibrary.pipeline.steps.kinds import FileArtifactStep, MissingOutput, Step

LOCK_HELD_REFUSAL = "another run holds this library"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRequest:
    """What one run was asked for: which targets, whether it starts over, and what it builds again."""

    targets: tuple[str, ...]
    from_scratch: bool
    redo: tuple[str, ...]
    follow: bool


@dataclass(frozen=True)
class RunReport:
    """What one run decided about every step it reached, and how it ended."""

    outcome: RunOutcome
    verdicts: Mapping[str, StepVerdict]
    attempts: tuple[Attempt, ...]
    refusal: str

    @property
    def exit_status(self) -> ExitStatus:
        """The status the pipeline command ends with, named after what stopped the run."""
        match self.outcome:
            case RunOutcome.COMPLETED:
                return ExitStatus.COMPLETED
            case RunOutcome.REFUSED:
                return ExitStatus.REFUSED
            case RunOutcome.LOCK_LOST:
                return ExitStatus.FAILED
        if self.refusal:
            return ExitStatus.REFUSED
        last = self.attempts[-1].outcome if self.attempts else AttemptOutcome.FAILED
        return STOPPING_STATUSES.get(last, ExitStatus.FAILED)


STOPPING_STATUSES: Mapping[AttemptOutcome, ExitStatus] = {
    AttemptOutcome.REFUSED: ExitStatus.REFUSED,
    AttemptOutcome.MEMORY_CAP_REACHED: ExitStatus.MEMORY_CAP_REACHED,
    AttemptOutcome.INTERRUPTED: ExitStatus.INTERRUPTED,
}


@dataclass(frozen=True)
class _Taken:
    """What became of one step a run reached."""

    verdict: StepVerdict
    attempt: Attempt | None
    refusal: str

    @property
    def settled(self) -> bool:
        """Whether the step stands done, which lets the run go on to the next."""
        if self.verdict is StepVerdict.RAN:
            return self.attempt is not None and self.attempt.completed
        return self.verdict in (StepVerdict.SATISFIED, StepVerdict.RESEALED)


def run_pipeline(
    session: RunSession, graph: StepGraph, request: RunRequest, sinks: Sinks, lock: PipelineLock | None
) -> RunReport:
    """Take every step of the named targets in order, running the ones with work left.

    A step decides for itself whether it is done, from the outputs it stands for rather than from
    anything this run remembers. The first step that fails, refuses or is interrupted ends the run
    and every later step is recorded as unreached, so a relaunch takes up exactly there. Every
    durable effect is made before the event reporting it, so a run that dies at any moment leaves a
    library a later run reads correctly.
    """
    steps = graph.order(request.targets)
    sinks.emit(
        RunStarted(
            run_id=session.run.run_id,
            targets=request.targets or ("all",),
            steps=tuple(step.name for step in steps),
        )
    )
    if lock is None:
        return refuse_run(sinks, LOCK_HELD_REFUSAL)
    sinks.emit(LockAcquired())
    running = _steps_already_running(session, graph)
    if running:
        return refuse_run(sinks, f"{', '.join(running)} is still running from an earlier run of this library")
    redo_refusal = _redo_refusal(graph, request)
    if redo_refusal is not None:
        return refuse_run(sinks, redo_refusal)

    if request.from_scratch or scratch_is_unfinished(session.context.layout):
        stopped = start_from_scratch(session, sinks)
        if stopped is not None:
            sinks.emit(RunEnded(outcome=RunOutcome.STOPPED))
            return RunReport(outcome=RunOutcome.STOPPED, verdicts={}, attempts=(stopped,), refusal="")
    _apply_redo(session, graph, request, sinks)
    return _take_in_order(session, steps, request, sinks, lock)


def refuse_run(sinks: Sinks, reason: str) -> RunReport:
    """End a run before any step, naming what a person settles first."""
    sinks.emit(RunRefused(reason=reason))
    sinks.emit(RunEnded(outcome=RunOutcome.REFUSED))
    return RunReport(outcome=RunOutcome.REFUSED, verdicts={}, attempts=(), refusal=reason)


def _take_in_order(
    session: RunSession, steps: tuple[Step, ...], request: RunRequest, sinks: Sinks, lock: PipelineLock
) -> RunReport:
    verdicts: dict[str, StepVerdict] = {}
    attempts: list[Attempt] = []
    for index, step in enumerate(steps):
        if not lock.held():
            _leave_unreached(steps[index:], verdicts, sinks)
            sinks.emit(LockLost())
            sinks.emit(RunEnded(outcome=RunOutcome.LOCK_LOST))
            return RunReport(outcome=RunOutcome.LOCK_LOST, verdicts=verdicts, attempts=tuple(attempts), refusal="")

        taken = _take(session, step, sinks, follow=request.follow)
        verdicts[step.name] = taken.verdict
        if taken.attempt is not None:
            attempts.append(taken.attempt)
        if taken.settled:
            continue
        _leave_unreached(steps[index + 1 :], verdicts, sinks)
        sinks.emit(RunEnded(outcome=RunOutcome.STOPPED))
        return RunReport(outcome=RunOutcome.STOPPED, verdicts=verdicts, attempts=tuple(attempts), refusal=taken.refusal)

    sinks.emit(RunEnded(outcome=RunOutcome.COMPLETED))
    return RunReport(outcome=RunOutcome.COMPLETED, verdicts=verdicts, attempts=tuple(attempts), refusal="")


def _leave_unreached(steps: tuple[Step, ...], verdicts: dict[str, StepVerdict], sinks: Sinks) -> None:
    """Record every step a stopped run never reached, so its account names every step of its targets."""
    for step in steps:
        verdicts[step.name] = StepVerdict.NOT_REACHED
        sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.NOT_REACHED, reasons=()))


def _take(session: RunSession, step: Step, sinks: Sinks, *, follow: bool) -> _Taken:
    """Decide one step and carry out whatever it says is left, reporting how it went."""
    plan = step.evaluate(session.context)
    sinks.emit(InputsEvaluated(step=step.name, inputs=dict(plan.inputs), digest=plan.digest))
    match plan.action:
        case StepAction.SKIP:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.SATISFIED, reasons=()))
            return _Taken(verdict=StepVerdict.SATISFIED, attempt=None, refusal="")
        case StepAction.REFUSE:
            refusal = f"{step.name}: {plan.reason}"
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.REFUSED, reasons=()))
            sinks.emit(RunRefused(reason=refusal))
            return _Taken(verdict=StepVerdict.REFUSED, attempt=None, refusal=refusal)
        case StepAction.SEAL:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.RESEALED, reasons=tuple(sorted(plan.reasons))))
            sealed = _sealed(session, step, plan, sinks)
            return _Taken(verdict=StepVerdict.RESEALED if sealed else StepVerdict.RAN, attempt=None, refusal="")
        case StepAction.RUN:
            sinks.emit(StepDecided(step=step.name, verdict=StepVerdict.RAN, reasons=tuple(sorted(plan.reasons))))
            return _Taken(verdict=StepVerdict.RAN, attempt=_run(session, step, plan, sinks, follow=follow), refusal="")


def _run(session: RunSession, step: Step, plan: StepPlan, sinks: Sinks, *, follow: bool) -> Attempt:
    """Run one step's command, then bind what it produced to the inputs it was built from."""
    sinks.emit(
        AttemptStarted(
            step=step.name,
            argv=plan.argv,
            log=str(session.run.log(step.name)),
            scope=session.context.scope_name(step.name),
        )
    )
    attempt = run_step_command(session, step=step.name, command=plan.argv, follow=follow)
    if attempt.completed and not _sealed(session, step, plan, sinks):
        attempt = _without_output(attempt)
    record_attempt(session.run.attempts, attempt)
    sinks.emit(AttemptEnded(step=step.name, outcome=attempt.outcome, exit_status=attempt.exit_status))
    return attempt


def _sealed(session: RunSession, step: Step, plan: StepPlan, sinks: Sinks) -> bool:
    """Bind a step's output to its inputs, reporting whether the output was there to bind."""
    try:
        outputs = step.seal(session.context, plan)
    except MissingOutput as error:
        _logger.error("%s", error)
        return False
    write_step_record(session.context.layout.step_record(step.name), inputs=plan.inputs, outputs=outputs)
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


def _redo_refusal(graph: StepGraph, request: RunRequest) -> str | None:
    """Why the steps a run is asked to build again cannot be, where one of them cannot."""
    if request.redo and request.from_scratch:
        return "--redo and --from-scratch ask for two different runs; a run from scratch builds every step again"
    reached = {step.name for step in graph.order(request.targets)}
    for name in request.redo:
        if name not in reached:
            return f"{name} is outside the targets this run takes"
        if not isinstance(graph.step(name), FileArtifactStep):
            return f"{name} builds nothing of its own to drop; --redo names a step that builds a file or a directory"
    return None


def _apply_redo(session: RunSession, graph: StepGraph, request: RunRequest, sinks: Sinks) -> None:
    """Drop what the named steps built, so this run builds it again."""
    for name in request.redo:
        step = graph.step(name)
        if isinstance(step, FileArtifactStep):
            step.forget(session.context)
            sinks.emit(RedoApplied(step=name))


def _steps_already_running(session: RunSession, graph: StepGraph) -> tuple[str, ...]:
    """The steps of this library another process still holds, which a run leaves alone."""
    names = (RESET_STEP, *(step.name for step in graph.steps))
    context = session.context
    return tuple(name for name in names if step_is_running(context.connection, context.scope_name(name)))
