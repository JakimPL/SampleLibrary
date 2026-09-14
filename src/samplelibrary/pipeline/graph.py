from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from samplelibrary.pipeline.steps.kinds import Step

ALL_TARGET: Final[str] = "all"


class UnknownTarget(ValueError):
    """Raised when a run names a target or a step this pipeline does not hold."""


class MalformedGraph(ValueError):
    """Raised when the steps of a pipeline require one another in a way no order satisfies."""


@dataclass(frozen=True)
class StepGraph:
    """Every step a pipeline holds, what each needs before it, the targets a run names them by, and what it owns.

    `owned_outputs` are the patterns, under the library root, of everything the steps build, which a
    run from scratch removes along with whatever else the pipeline sealed.

    Steps are declared in the order they read, and a run keeps that order wherever the requirements
    leave a choice, so two runs over one target do the same things in the same sequence.
    """

    steps: tuple[Step, ...]
    targets: Mapping[str, tuple[str, ...]]
    owned_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        names = [step.name for step in self.steps]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise MalformedGraph(f"more than one step is called {', '.join(repeated)}")
        known = set(names)
        for step in self.steps:
            unknown = sorted(set(step.requires) - known)
            if unknown:
                raise MalformedGraph(f"{step.name} requires {', '.join(unknown)}, which this pipeline does not hold")
        for target, members in self.targets.items():
            unknown = sorted(set(members) - known)
            if unknown:
                raise MalformedGraph(
                    f"the {target} target names {', '.join(unknown)}, which this pipeline does not hold"
                )
        self._require_an_order(names)

    def _require_an_order(self, names: Sequence[str]) -> None:
        """Make sure the requirements can be met at all.

        Raises:
            MalformedGraph: the steps require one another in a circle.
        """
        settled: set[str] = set()
        remaining = list(names)
        while remaining:
            ready = [name for name in remaining if set(self.step(name).requires) <= settled]
            if not ready:
                raise MalformedGraph(f"these steps require one another in a circle: {', '.join(sorted(remaining))}")
            settled.update(ready)
            remaining = [name for name in remaining if name not in settled]

    def step(self, name: str) -> Step:
        """The step of this name.

        Raises:
            UnknownTarget: this pipeline holds no such step.
        """
        for step in self.steps:
            if step.name == name:
                return step
        raise UnknownTarget(f"this pipeline holds no step called {name}")

    def order(self, targets: Sequence[str]) -> tuple[Step, ...]:
        """Every step the named targets need, in the order a run takes them.

        Raises:
            UnknownTarget: a name is neither a target nor a step of this pipeline.
        """
        wanted: set[str] = set()
        for target in targets or (ALL_TARGET,):
            wanted.update(self._members(target))
        needed = set(wanted)
        while True:
            required = {name for member in needed for name in self.step(member).requires}
            if required <= needed:
                break
            needed |= required
        return tuple(step for step in self.steps if step.name in needed)

    def descendants(self, name: str) -> frozenset[str]:
        """Every step that needs this one, directly or through another."""
        reached = {name}
        while True:
            grown = reached | {step.name for step in self.steps if set(step.requires) & reached}
            if grown == reached:
                return frozenset(reached - {name})
            reached = grown

    def _members(self, target: str) -> tuple[str, ...]:
        if target in self.targets:
            return self.targets[target]
        if any(step.name == target for step in self.steps):
            return (target,)
        known = ", ".join(sorted({*self.targets, *(step.name for step in self.steps)}))
        raise UnknownTarget(f"{target} is neither a target nor a step; this pipeline holds {known}")
