from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Final

from samplecore.digests import digest_of_rows

DIGEST_CHARACTERS: Final[int] = 16


@unique
class AttemptOutcome(StrEnum):
    """How one attempt at a step ended, read from the exit status of the process that made it."""

    COMPLETED = "completed"
    FAILED = "failed"
    REFUSED = "refused"
    INTERRUPTED = "interrupted"
    MEMORY_CAP_REACHED = "memory cap reached"
    NO_OUTPUT = "no output"


@unique
class StepAction(StrEnum):
    """What a step says is left to do about itself, before a run acts on it."""

    SKIP = "skip"
    RUN = "run"
    SEAL = "seal"
    REFUSE = "refuse"


@unique
class StepVerdict(StrEnum):
    """What a run decided about one step."""

    SATISFIED = "satisfied"
    RAN = "ran"
    RESEALED = "resealed"
    REFUSED = "refused"
    NOT_REACHED = "not reached"


@unique
class RunOutcome(StrEnum):
    """How a whole run ended."""

    COMPLETED = "completed"
    STOPPED = "stopped"
    REFUSED = "refused"
    LOCK_LOST = "lock lost"


def input_digest(inputs: Mapping[str, str]) -> str:
    """The name a step's inputs go by: one digest over every named component, in name order."""
    return digest_of_rows(sorted(inputs.items()))[:DIGEST_CHARACTERS]


def changed_components(inputs: Mapping[str, str], recorded: Mapping[str, str]) -> frozenset[str]:
    """Which named inputs a step sees differently now than the record of its last complete run holds."""
    return frozenset(name for name in inputs.keys() | recorded.keys() if inputs.get(name) != recorded.get(name))


@dataclass(frozen=True)
class StepPlan:
    """What a step decided about itself before a run acts on it: its inputs now, and what is left to do.

    `argv` is the command line the step runs when it has work; a step with nothing to do names none.
    `reasons` are the input components that moved since the step last finished, which is what
    `status` reports, and `reason` says in words why a step refuses.
    """

    inputs: Mapping[str, str]
    action: StepAction
    argv: tuple[str, ...] = ()
    reasons: frozenset[str] = field(default_factory=frozenset)
    reason: str = ""

    @property
    def digest(self) -> str:
        return input_digest(self.inputs)
