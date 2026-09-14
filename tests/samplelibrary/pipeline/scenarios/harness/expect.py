from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome, RunOutcome, StepVerdict
from tests.samplelibrary.pipeline.scenarios.harness.observe import RunObservation
from tests.samplelibrary.pipeline.scenarios.harness.world import PARTS


@dataclass(frozen=True)
class Expect:
    """What a run must have done, stated for every step of its targets, and how the catalog moved.

    The verdicts are total: a scenario says what became of every step, so a step running where it
    was expected to stand satisfied fails the scenario rather than passing unnoticed. The delta is
    total too: every part of the catalog a scenario leaves unnamed must stay where it was.
    """

    outcome: RunOutcome | None
    exit_status: int
    steps: Mapping[str, StepVerdict]
    outcomes: Mapping[str, AttemptOutcome] = field(default_factory=dict)
    reasons: Mapping[str, frozenset[str]] = field(default_factory=dict)
    refusal: str | None = None
    moved: frozenset[str] = frozenset()

    @classmethod
    def completed(cls, steps: tuple[str, ...], verdict: StepVerdict) -> Expect:
        """A completed run giving every step one verdict, which is what a first and a settled run each look like."""
        return cls(
            outcome=RunOutcome.COMPLETED,
            exit_status=ExitStatus.COMPLETED,
            steps={step: verdict for step in steps},
        )

    @classmethod
    def observed(cls, observation: RunObservation) -> Expect:
        """What a run did, read back as an expectation, for holding a run nobody stated anything about to the oracles."""
        return cls(
            outcome=observation.outcome,
            exit_status=observation.exit_status,
            steps=observation.verdicts,
            outcomes=observation.outcomes,
        )

    @classmethod
    def refused_run(cls, refusal: str) -> Expect:
        """A run refused before it decided any step, naming why."""
        return cls(outcome=RunOutcome.REFUSED, exit_status=ExitStatus.REFUSED, steps={}, refusal=refusal)

    def with_steps(self, **verdicts: StepVerdict) -> Expect:
        """The same expectation with these steps read differently; underscores stand for hyphens."""
        return replace(self, steps={**self.steps, **_hyphenated(verdicts)})

    def stopped_at(self, step: str, outcome: AttemptOutcome, exit_status: int, *, after: tuple[str, ...]) -> Expect:
        """The same run stopped by one step's attempt, with every step after it unreached."""
        steps = dict(self.steps)
        steps[step] = StepVerdict.RAN
        steps.update({later: StepVerdict.NOT_REACHED for later in after})
        return replace(
            self,
            outcome=RunOutcome.STOPPED,
            exit_status=exit_status,
            steps=steps,
            outcomes={**self.outcomes, step: outcome},
        )

    def refused_at(self, step: str, refusal: str, *, after: tuple[str, ...]) -> Expect:
        """The same run stopped by a step refusing before it ran, with every step after it unreached."""
        steps = dict(self.steps)
        steps[step] = StepVerdict.REFUSED
        steps.update({later: StepVerdict.NOT_REACHED for later in after})
        return replace(
            self,
            outcome=RunOutcome.STOPPED,
            exit_status=ExitStatus.REFUSED,
            steps=steps,
            refusal=refusal,
        )

    def killed(self) -> Expect:
        """The same run, its own process killed before it could say how it ended."""
        return replace(self, outcome=None, exit_status=-9)

    def ending(self, **outcomes: AttemptOutcome) -> Expect:
        """The same expectation, naming how these steps' attempts ended."""
        return replace(self, outcomes={**self.outcomes, **_hyphenated(outcomes)})

    def because(self, **reasons: frozenset[str]) -> Expect:
        """The same expectation, naming exactly which inputs these steps ran because of."""
        return replace(self, reasons={**self.reasons, **_hyphenated(reasons)})

    def moving(self, *parts: str) -> Expect:
        """The same expectation, naming the parts of the catalog the act moves."""
        unknown = set(parts) - set(PARTS)
        assert not unknown, f"no part of the catalog is called {', '.join(sorted(unknown))}"
        return replace(self, moved=frozenset(parts))


def _hyphenated[T](values: Mapping[str, T]) -> dict[str, T]:
    return {name.replace("_", "-"): value for name, value in values.items()}
