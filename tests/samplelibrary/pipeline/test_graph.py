from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.graph import ALL_TARGET, MalformedGraph, StepGraph, UnknownTarget
from samplelibrary.pipeline.results import StepAction, StepPlan


@dataclass(frozen=True)
class NamedStep:
    """A step standing for its place in a graph, which is all a graph reads of one."""

    name: str
    requires: tuple[str, ...] = ()

    def evaluate(self, context: PipelineContext) -> StepPlan:
        return StepPlan(inputs={}, action=StepAction.SKIP)

    def seal(self, context: PipelineContext, plan: StepPlan) -> dict[str, str]:
        return {}


def _graph() -> StepGraph:
    steps = (
        NamedStep("labels"),
        NamedStep("modules", ("labels",)),
        NamedStep("files", ("labels",)),
        NamedStep("teacher", ("modules", "files")),
        NamedStep("descriptor", ("teacher",)),
    )
    return StepGraph(
        steps=steps,
        owned_outputs=(),
        targets={
            "catalog": ("labels", "modules", "files"),
            "cloud": ("descriptor",),
            ALL_TARGET: tuple(step.name for step in steps),
        },
    )


def test_a_target_brings_every_step_it_needs_in_the_order_they_are_declared() -> None:
    assert [step.name for step in _graph().order(("cloud",))] == [
        "labels",
        "modules",
        "files",
        "teacher",
        "descriptor",
    ]


def test_a_run_naming_no_target_takes_every_step() -> None:
    assert len(_graph().order(())) == 5


def test_a_step_may_be_named_in_place_of_a_target() -> None:
    assert [step.name for step in _graph().order(("modules",))] == ["labels", "modules"]


def test_every_step_that_needs_one_is_named_its_descendant() -> None:
    assert _graph().descendants("modules") == frozenset({"teacher", "descriptor"})
    assert _graph().descendants("descriptor") == frozenset()


def test_a_name_that_is_neither_a_target_nor_a_step_is_refused() -> None:
    with pytest.raises(UnknownTarget, match="neither a target nor a step"):
        _graph().order(("cloudy",))


@pytest.mark.parametrize(
    ("steps", "reason"),
    [
        ((NamedStep("one"), NamedStep("one")), "more than one step"),
        ((NamedStep("one", ("absent",)),), "which this pipeline does not hold"),
        ((NamedStep("one", ("two",)), NamedStep("two", ("one",))), "require one another in a circle"),
    ],
    ids=("a repeated name", "an unknown requirement", "a circle"),
)
def test_a_graph_no_order_satisfies_is_refused(steps: tuple[NamedStep, ...], reason: str) -> None:
    with pytest.raises(MalformedGraph, match=reason):
        StepGraph(steps=steps, owned_outputs=(), targets={})


def test_a_target_naming_an_unknown_step_is_refused() -> None:
    with pytest.raises(MalformedGraph, match="the cloud target names"):
        StepGraph(steps=(NamedStep("one"),), owned_outputs=(), targets={"cloud": ("two",)})
