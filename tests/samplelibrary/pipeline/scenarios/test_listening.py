from __future__ import annotations

from samplecloud.suggestions.scoring import DEFAULT_SUGGESTION_COUNT
from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome, StepVerdict
from samplelibrary.pipeline.steps.kinds import NOT_SHOWN, SAMPLES_TO_DESCRIBE
from samplelibrary.pipeline.steps.library import CATALOG_STEPS
from samplelibrary.pipeline.steps.listening import HEARD_VECTORS, HEARING_TEACHER_KEY, PARAMETERS, TEACHER_KEY
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan, GateMoment, ScriptedEffect, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner, wait_until_released
from tests.samplelibrary.pipeline.scenarios.harness.stand_ins import MIDWAY_CHECKPOINT_INTERVAL
from tests.samplelibrary.pipeline.scenarios.harness.stories import KILLED
from tests.samplelibrary.pipeline.scenarios.harness.world import DEFAULT_PIPELINE_TABLE, World

ORPHAN_DEADLINE_SECONDS = 60.0

LISTENING = ("teacher", "hearing-teacher", "suggestions")
LISTENING_TARGETS = ("catalog", "teacher", "suggestions")
EVERY_STEP = (*CATALOG_STEPS, *LISTENING)
BUILT = Expect.completed(EVERY_STEP, StepVerdict.RAN).with_steps(labels=StepVerdict.SATISFIED)
SETTLED = BUILT.with_steps(
    teacher=StepVerdict.SATISFIED, hearing_teacher=StepVerdict.SATISFIED, suggestions=StepVerdict.SATISFIED
)
FIRST_BUILD = BUILT.moving("modules", "samples", "relations", "files", "passes", "experiments", "suggestions")


def test_a_first_run_hears_every_readable_sample_twice_and_ranks_labels_for_them(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(Run(targets=LISTENING_TARGETS), FIRST_BUILD, story="the first run")

    runner.run(Run(targets=LISTENING_TARGETS), SETTLED, story="the run after it")
    teacher = world.experiment_by_key(TEACHER_KEY)
    heard = world.experiment_by_key(HEARING_TEACHER_KEY)
    assert teacher is not None and heard is not None
    assert teacher[1] == heard[1] > 0


def test_a_sample_file_added_grows_both_readings_under_their_keys_and_ranks_again(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(Run(targets=LISTENING_TARGETS), FIRST_BUILD, story="the first run")
    teacher = world.experiment_by_key(TEACHER_KEY)
    assert teacher is not None

    world.add_pack_file()

    runner.run(
        Run(targets=LISTENING_TARGETS),
        BUILT.because(
            teacher=frozenset({SAMPLES_TO_DESCRIBE}),
            hearing_teacher=frozenset({SAMPLES_TO_DESCRIBE}),
            suggestions=frozenset({HEARD_VECTORS}),
        ).moving("samples", "files", "passes", "experiments", "suggestions"),
        story="the run after a sample file arrived",
    )
    assert world.experiment_by_key(TEACHER_KEY) == (teacher[0], teacher[1] + 1)


def test_a_reading_that_ended_a_success_without_its_experiment_stops_the_run(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(
        Run(targets=LISTENING_TARGETS, faults=FaultPlan(steps={"teacher": StepFault(effect=ScriptedEffect.NO_OUTPUT)})),
        BUILT.stopped_at(
            "teacher", AttemptOutcome.NO_OUTPUT, ExitStatus.FAILED, after=("hearing-teacher", "suggestions")
        ).moving("modules", "samples", "relations", "files", "passes"),
        story="a run whose teacher files nothing",
    )

    runner.run(
        Run(targets=LISTENING_TARGETS),
        BUILT.moving("experiments", "suggestions"),
        story="the relaunch",
    )


def test_an_interrupted_reading_keeps_what_it_committed_and_the_relaunch_reads_the_rest(
    runner: ScenarioRunner, world: World
) -> None:
    host = runner.start(
        Run(targets=LISTENING_TARGETS, faults=FaultPlan(steps={"hearing-teacher": StepFault(gate=GateMoment.MIDWAY)}))
    )
    host.wait_at("hearing-teacher", GateMoment.MIDWAY)
    host.interrupt()
    runner.finish(
        host,
        BUILT.stopped_at(
            "hearing-teacher", AttemptOutcome.INTERRUPTED, ExitStatus.INTERRUPTED, after=("suggestions",)
        ).moving("modules", "samples", "relations", "files", "passes", "experiments"),
        story="the run interrupted partway through hearing",
    )
    interrupted = world.experiment_by_key(HEARING_TEACHER_KEY)
    assert interrupted is not None and interrupted[1] == MIDWAY_CHECKPOINT_INTERVAL

    runner.run(
        Run(targets=LISTENING_TARGETS),
        BUILT.with_steps(teacher=StepVerdict.SATISFIED).moving("experiments", "suggestions"),
        story="the relaunch",
    )
    resumed = world.experiment_by_key(HEARING_TEACHER_KEY)
    teacher = world.experiment_by_key(TEACHER_KEY)
    assert resumed is not None and teacher is not None
    assert resumed == (interrupted[0], teacher[1])


def test_a_reading_whose_run_died_after_it_committed_stands_satisfied(runner: ScenarioRunner, world: World) -> None:
    host = runner.start(
        Run(targets=LISTENING_TARGETS, faults=FaultPlan(steps={"teacher": StepFault(gate=GateMoment.AFTER_OUTPUT)}))
    )
    host.wait_at("teacher", GateMoment.AFTER_OUTPUT)
    host.kill()
    runner.finish(
        host,
        Expect(
            outcome=None, exit_status=KILLED, steps={name: BUILT.steps[name] for name in (*CATALOG_STEPS, "teacher")}
        ).moving("modules", "samples", "relations", "files", "passes", "experiments"),
        story="the run killed as the teacher finished",
    )
    host.release("teacher", GateMoment.AFTER_OUTPUT)
    wait_until_released(world, ORPHAN_DEADLINE_SECONDS)

    runner.run(
        Run(targets=LISTENING_TARGETS),
        BUILT.with_steps(teacher=StepVerdict.SATISFIED).moving("experiments", "suggestions"),
        story="the relaunch",
    )


def test_suggestion_parameters_name_their_scoring_and_an_earlier_one_is_shown_again(
    runner: ScenarioRunner, world: World
) -> None:
    runner.run(Run(targets=LISTENING_TARGETS), FIRST_BUILD, story="the first run")

    world.set_pipeline_table(f"{DEFAULT_PIPELINE_TABLE}\n[pipeline.suggestions]\ntop = 5\n")
    runner.run(
        Run(targets=LISTENING_TARGETS),
        SETTLED.with_steps(suggestions=StepVerdict.RAN)
        .because(suggestions=frozenset({PARAMETERS}))
        .moving("experiments", "suggestions"),
        story="the run keeping five labels a sample",
    )

    world.set_pipeline_table(f"{DEFAULT_PIPELINE_TABLE}\n[pipeline.suggestions]\ntop = {DEFAULT_SUGGESTION_COUNT}\n")
    runner.run(
        Run(targets=LISTENING_TARGETS),
        SETTLED.with_steps(suggestions=StepVerdict.RAN)
        .because(suggestions=frozenset({NOT_SHOWN}))
        .moving("suggestions"),
        story="the run writing the default out, which shows the first scoring again",
    )

    world.set_pipeline_table(DEFAULT_PIPELINE_TABLE)
    runner.run(Run(targets=LISTENING_TARGETS), SETTLED, story="the run leaving the default unsaid")


def test_a_vocabulary_that_cannot_be_read_refuses_the_suggestions(runner: ScenarioRunner, world: World) -> None:
    runner.run(Run(targets=LISTENING_TARGETS), FIRST_BUILD, story="the first run")
    world.set_pipeline_table(
        f'{DEFAULT_PIPELINE_TABLE}\n[pipeline.suggestions]\nvocabulary = "{(world.root / "missing.txt").as_posix()}"\n'
    )

    runner.run(
        Run(targets=LISTENING_TARGETS),
        SETTLED.refused_at("suggestions", "missing.txt", after=()),
        story="a run ranking against a missing vocabulary file",
    )
