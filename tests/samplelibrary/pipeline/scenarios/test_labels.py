from __future__ import annotations

from samplelibrary.pipeline.results import StepVerdict
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, FIRST_BUILD, after, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import World

IMPORTED = BUILT.with_steps(labels=StepVerdict.RAN).moving("labels")
REFUSING_LABELS = BUILT.refused_at("labels", "", after=after("labels"))


def _labels_read_in(runner: ScenarioRunner, world: World) -> None:
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")
    world.write_labels_file("WARM PAD")
    runner.run(Run(targets=CATALOG), IMPORTED, story="the run reading the labels in")


def test_labels_the_configuration_names_are_read_in_once(runner: ScenarioRunner, world: World) -> None:
    _labels_read_in(runner, world)

    runner.run(Run(targets=CATALOG), BUILT, story="the run after it")


def test_a_labels_file_that_is_not_there_refuses_the_run(runner: ScenarioRunner, world: World) -> None:
    world.labels = True
    world.write_config()

    runner.run(
        Run(targets=CATALOG, faults=scripted()),
        BUILT.refused_at("labels", "is not there", after=after("labels")),
        story="a run naming a labels file that is not there",
    )


def test_labels_made_in_the_app_refuse_a_file_never_read_into_the_library(runner: ScenarioRunner, world: World) -> None:
    """Reading the file in would put its older decisions over a person's newer ones."""
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")
    world.label_a_sample("SNARE")
    world.write_labels_file("WARM PAD")

    runner.run(
        Run(targets=CATALOG),
        BUILT.refused_at("labels", "already holds labels of its own", after=after("labels")),
        story="a run naming a file over labels of the library's own",
    )


def test_a_labels_file_edited_after_it_was_read_in_refuses_the_run(runner: ScenarioRunner, world: World) -> None:
    _labels_read_in(runner, world)
    world.write_labels_file("COLD PAD")

    runner.run(
        Run(targets=CATALOG),
        BUILT.refused_at("labels", "already holds labels of its own", after=after("labels")),
        story="a run naming the edited file",
    )


def test_the_same_labels_under_another_name_stand_read_in(runner: ScenarioRunner, world: World) -> None:
    _labels_read_in(runner, world)
    world.move_labels_file("labels-moved.jsonl")

    runner.run(Run(targets=CATALOG), BUILT, story="a run naming the moved file")


def test_a_label_changed_in_the_app_after_the_file_was_read_in_stays_changed(
    runner: ScenarioRunner, world: World
) -> None:
    _labels_read_in(runner, world)
    world.label_a_sample("BRIGHT PAD")

    runner.run(Run(targets=CATALOG), BUILT, story="a run after the label changed")
