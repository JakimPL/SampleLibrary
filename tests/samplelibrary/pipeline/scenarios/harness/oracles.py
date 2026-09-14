from __future__ import annotations

from collections.abc import Mapping, Sequence

from samplelibrary.pipeline.events import event_json
from samplelibrary.pipeline.graph import StepGraph
from samplelibrary.pipeline.results import StepAction, StepVerdict
from samplelibrary.pipeline.status import StepStatus
from samplelibrary.pipeline.steps.kinds import PassStep
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.observe import Evidence, RunObservation
from tests.samplelibrary.pipeline.scenarios.harness.render import render_divergence


class Divergence(AssertionError):
    """Raised when a run did something other than its scenario says, told as the story of where."""


def check_expectation(observation: RunObservation, expect: Expect, story: str) -> None:
    """Hold a run to everything a scenario said about it, naming the act where it diverged."""
    problems: list[str] = []
    if observation.verdicts != dict(expect.steps):
        problems.append("the verdicts differ")
    if observation.outcome != expect.outcome:
        problems.append(f"the run ended {observation.outcome}, where {expect.outcome} was expected")
    if observation.exit_status != expect.exit_status:
        problems.append(f"the command exited {observation.exit_status}, where {expect.exit_status} was expected")
    for step, outcome in expect.outcomes.items():
        if observation.outcomes.get(step) != outcome:
            problems.append(f"{step} ended {observation.outcomes.get(step)}, where {outcome} was expected")
    for step, reasons in expect.reasons.items():
        if observation.reasons.get(step) != reasons:
            problems.append(f"{step} ran because {sorted(observation.reasons.get(step, ()))}, not {sorted(reasons)}")
    if expect.refusal is not None and (observation.refusal is None or expect.refusal not in observation.refusal):
        problems.append(f"the refusal read {observation.refusal!r}, where it should name {expect.refusal!r}")
    _raise_on(problems, story, observation, expect)


def check_evidence(observation: RunObservation, evidence: Evidence, story: str, expect: Expect) -> None:
    """Hold the run's own account against what it left behind, which it does not narrate.

    A step the run says ended left an attempt and a log; a step it says it skipped left
    neither; a scripted step that ran was one the run says it started; and the run's own event file
    holds every event the scenario saw it emit.
    """
    problems: list[str] = []
    started = list(observation.started)
    finished = [step for step, _ in observation.outcomes.items()]
    satisfied = {step for step, verdict in observation.verdicts.items() if verdict is StepVerdict.SATISFIED}
    if sorted(evidence.attempts) != sorted(finished):
        problems.append(f"attempts.jsonl names {list(evidence.attempts)}, the events ended {finished}")
    if not set(finished) <= set(evidence.logs):
        problems.append(f"the logs are {list(evidence.logs)}, the events ended {finished}")
    if satisfied & set(evidence.attempts):
        problems.append(f"satisfied steps {sorted(satisfied & set(evidence.attempts))} left attempts")
    if evidence.abandoned_gates:
        problems.append(f"{', '.join(evidence.abandoned_gates)} waited at a gate nobody released")
    if not set(evidence.ledger) <= set(started):
        problems.append(f"scripted steps {list(evidence.ledger)} ran, the events started {started}")
    if [event_json(event) for event in observation.recorded] != [event_json(event) for event in observation.events]:
        problems.append("the run's own events.jsonl differs from the events it emitted")
    _raise_on(problems, story, observation, expect)


def check_delta(before: Mapping[str, str], after: Mapping[str, str], expect: Expect, story: str) -> None:
    """Hold the catalog to the change a scenario declared, part by part.

    Anything a scenario leaves unsaid must not have moved, so a pass quietly rewriting the catalog
    fails the scenario it ran in.
    """
    moved = frozenset(part for part in before if before[part] != after[part])
    if moved != expect.moved:
        raise Divergence(
            f"{story}: the catalog moved {sorted(moved)}, where the scenario declared {sorted(expect.moved)}"
        )


def check_status_agreement(
    statuses: Sequence[StepStatus], observation: RunObservation, graph: StepGraph, story: str, expect: Expect
) -> None:
    """Hold what `status` said right before a run to what the run then did.

    A step status calls satisfied stands satisfied unless a step it needs ran first; one status says
    runs, runs, for at least the reasons status named; one it says seals, seals.
    """
    verdicts = observation.verdicts
    ran = {step for step, verdict in verdicts.items() if verdict in (StepVerdict.RAN, StepVerdict.RESEALED)}
    problems: list[str] = []
    for status in statuses:
        observed = verdicts.get(status.step)
        if observed is None or observed is StepVerdict.NOT_REACHED or status.waits_on:
            continue
        upstream_ran = bool(_upstream(graph, status.step) & ran)
        match status.action:
            case StepAction.SKIP if not upstream_ran and observed is not StepVerdict.SATISFIED:
                problems.append(f"status called {status.step} satisfied, the run said {observed}")
            case StepAction.RUN if observed is not StepVerdict.RAN and not upstream_ran:
                problems.append(f"status said {status.step} runs, the run said {observed}")
            case StepAction.RUN if not status.reasons <= observation.reasons.get(status.step, frozenset()):
                problems.append(f"status said {status.step} runs because {sorted(status.reasons)}")
            case StepAction.SEAL if observed is not StepVerdict.RESEALED:
                problems.append(f"status said {status.step} seals, the run said {observed}")
            case StepAction.REFUSE if observed is not StepVerdict.REFUSED:
                problems.append(f"status said {status.step} refuses, the run said {observed}")
    _raise_on(problems, story, observation, expect)


def check_settled(statuses: Sequence[StepStatus], graph: StepGraph, story: str) -> None:
    """After a completed run, `status` finds every step satisfied but the passes, which always run."""
    unsettled = [
        f"{status.step}: {status.described()}"
        for status in statuses
        if not isinstance(graph.step(status.step), PassStep) and status.action is not StepAction.SKIP
    ]
    if unsettled:
        raise Divergence(f"{story}: the run completed, yet status reads {unsettled}")


def check_hygiene(locks_held: Sequence[str], story: str) -> None:
    """Nothing of a run that ended outlives it: no step lock, and no pipeline lock."""
    if locks_held:
        raise Divergence(f"{story}: {', '.join(locks_held)} still held after the run ended")


def _upstream(graph: StepGraph, step: str) -> frozenset[str]:
    return frozenset(name for name in (other.name for other in graph.steps) if step in graph.descendants(name))


def _raise_on(problems: list[str], story: str, observation: RunObservation, expect: Expect) -> None:
    if problems:
        raise Divergence(render_divergence(story, problems, observation, expect))
