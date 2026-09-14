from __future__ import annotations

from samplecore.exit_status import ExitStatus
from samplelibrary.pipeline.results import AttemptOutcome, StepVerdict
from samplelibrary.pipeline.steps.kinds import SAMPLES_TO_DESCRIBE, SEALED_COPY_MISSING
from samplelibrary.pipeline.steps.listening import TEACHER_KEY
from samplemorph.published import published_restorer_path
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.observe import ledger_commands
from tests.samplelibrary.pipeline.scenarios.harness.plans import FaultPlan, GateMoment, ScriptedEffect, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner, wait_until_released
from tests.samplelibrary.pipeline.scenarios.harness.stories import KILLED
from tests.samplelibrary.pipeline.scenarios.harness.world import World

EVERY_STEP = (
    "labels",
    "modules",
    "sample-files",
    "notes",
    "thumbnails",
    "equivalence",
    "relink",
    "teacher",
    "hearing-teacher",
    "suggestions",
    "grid-cache",
    "descriptor",
    "embedding",
    "completion",
    "evaluation",
    "module-evaluation",
    "cloud",
    "module-placeholders",
    "morph-codec",
    "restorer",
    "morph-models",
)
PASSES = ("modules", "sample-files", "notes", "thumbnails", "equivalence", "relink", "module-placeholders")
SETTLED = Expect.completed(EVERY_STEP, StepVerdict.SATISFIED).with_steps(
    **{step.replace("-", "_"): StepVerdict.RAN for step in PASSES}
)
# The embedding describes every sample the cache holds, which is every sample the library can read,
# so the completion finds nothing left to describe.
BUILT = Expect.completed(EVERY_STEP, StepVerdict.RAN).with_steps(
    labels=StepVerdict.SATISFIED, completion=StepVerdict.SATISFIED
)
EVERYTHING = ("modules", "samples", "relations", "files", "passes", "experiments", "suggestions", "cloud", "artifacts")
FROM_THE_DESCRIPTOR = ("descriptor", "embedding", "evaluation", "module-evaluation", "cloud")
ORPHAN_DEADLINE_SECONDS = 60.0


def _after(step: str) -> tuple[str, ...]:
    return EVERY_STEP[EVERY_STEP.index(step) + 1 :]


def _running(*steps: str) -> dict[str, StepVerdict]:
    return {step.replace("-", "_"): StepVerdict.RAN for step in steps}


def _built(runner: ScenarioRunner) -> None:
    runner.run(Run(), BUILT.moving(*EVERYTHING), story="the first run")


def test_one_command_builds_the_whole_library_and_a_second_finds_it_built(runner: ScenarioRunner) -> None:
    _built(runner)

    runner.run(Run(), SETTLED, story="the run after it")


def test_a_sample_file_added_rebuilds_exactly_what_the_new_sample_reaches(runner: ScenarioRunner, world: World) -> None:
    """The listening readings grow under their keys; everything named by the readable samples is built anew beside the old."""
    _built(runner)
    teacher = world.experiment_by_key(TEACHER_KEY)
    first_cloud = world.step_outputs("cloud")["experiment"]
    first_descriptor = world.step_outputs("descriptor")["sealed"]
    assert teacher is not None

    world.add_pack_file()

    runner.run(
        Run(),
        BUILT.because(
            teacher=frozenset({SAMPLES_TO_DESCRIBE}),
            hearing_teacher=frozenset({SAMPLES_TO_DESCRIBE}),
            suggestions=frozenset({"heard vectors"}),
            grid_cache=frozenset({"readable samples"}),
            descriptor=frozenset({"grid cache", "teacher vectors"}),
            embedding=frozenset({"descriptor", "grid cache"}),
            evaluation=frozenset({"experiment", "vectors"}),
            module_evaluation=frozenset({"experiment", "vectors"}),
            cloud=frozenset({"vectors"}),
            morph_codec=frozenset({"readable samples"}),
            restorer=frozenset({"readable samples"}),
            morph_models=frozenset({"codec", "restorer"}),
        ).moving("samples", "files", "passes", "experiments", "suggestions", "cloud", "artifacts"),
        story="the run after a sample file arrived",
    )

    assert world.experiment_by_key(TEACHER_KEY) == (teacher[0], teacher[1] + 1)
    assert world.step_outputs("cloud")["experiment"] != first_cloud
    assert world.experiment_by_key(first_cloud) is not None
    assert (world.library_root / "models" / "descriptors" / first_descriptor).is_file()


def test_a_descriptor_training_interrupted_partway_continues_from_its_last_epoch(
    runner: ScenarioRunner, world: World
) -> None:
    host = runner.start(Run(faults=FaultPlan(steps={"descriptor": StepFault(gate=GateMoment.MIDWAY)})))
    host.wait_at("descriptor", GateMoment.MIDWAY)
    host.interrupt()
    runner.finish(
        host,
        BUILT.stopped_at(
            "descriptor", AttemptOutcome.INTERRUPTED, ExitStatus.INTERRUPTED, after=_after("descriptor")
        ).moving("modules", "samples", "relations", "files", "passes", "experiments", "suggestions", "artifacts"),
        story="the run interrupted during the descriptor's training",
    )

    relaunch = runner.start(Run())
    runner.finish(
        relaunch,
        SETTLED.with_steps(**_running(*FROM_THE_DESCRIPTOR, "morph-codec", "restorer", "morph-models")).moving(
            "experiments", "cloud", "artifacts"
        ),
        story="the relaunch",
    )
    assert ledger_commands(relaunch.ledger)["descriptor"][-1] == "--resume"


def test_a_finished_training_whose_run_died_before_sealing_it_is_sealed_without_training(
    runner: ScenarioRunner, world: World
) -> None:
    host = runner.start(Run(faults=FaultPlan(steps={"descriptor": StepFault(gate=GateMoment.AFTER_OUTPUT)})))
    host.wait_at("descriptor", GateMoment.AFTER_OUTPUT)
    host.kill()
    runner.finish(
        host,
        Expect(
            outcome=None,
            exit_status=KILLED,
            steps={step: BUILT.steps[step] for step in EVERY_STEP[: EVERY_STEP.index("descriptor") + 1]},
        ).moving("modules", "samples", "relations", "files", "passes", "experiments", "suggestions", "artifacts"),
        story="the run killed as the descriptor finished training",
    )
    host.release("descriptor", GateMoment.AFTER_OUTPUT)
    wait_until_released(world, ORPHAN_DEADLINE_SECONDS)

    relaunch = runner.start(Run())
    runner.finish(
        relaunch,
        SETTLED.with_steps(
            descriptor=StepVerdict.RESEALED,
            **_running(
                "embedding", "evaluation", "module-evaluation", "cloud", "morph-codec", "restorer", "morph-models"
            ),
        ).moving("experiments", "cloud", "artifacts"),
        story="the relaunch",
    )
    assert "descriptor" not in ledger_commands(relaunch.ledger)


def test_a_descriptor_trained_again_into_the_same_bytes_leaves_everything_after_it_standing(
    runner: ScenarioRunner,
) -> None:
    _built(runner)

    runner.run(
        Run(redo=("descriptor",)),
        SETTLED.with_steps(descriptor=StepVerdict.RAN),
        story="the run redoing the descriptor",
    )


def test_a_descriptor_trained_again_into_other_bytes_rebuilds_what_reads_it_and_keeps_the_old_model(
    runner: ScenarioRunner, world: World
) -> None:
    _built(runner)
    first = world.step_outputs("descriptor")["sealed"]

    runner.run(
        Run(redo=("descriptor",), faults=FaultPlan(steps={"descriptor": StepFault(varies=True)})),
        SETTLED.with_steps(**_running(*FROM_THE_DESCRIPTOR)).moving("experiments", "cloud", "artifacts"),
        story="the run redoing the descriptor into other bytes",
    )

    assert world.step_outputs("descriptor")["sealed"] != first
    assert (world.library_root / "models" / "descriptors" / first).is_file()


def test_a_label_changed_in_the_app_teaches_the_descriptor_again(runner: ScenarioRunner, world: World) -> None:
    _built(runner)
    world.label_a_sample("SNARE")

    runner.run(
        Run(faults=FaultPlan(steps={"descriptor": StepFault(varies=True)})),
        SETTLED.with_steps(**_running(*FROM_THE_DESCRIPTOR))
        .because(descriptor=frozenset({"labels"}), evaluation=frozenset({"experiment", "labels"}))
        .moving("experiments", "cloud", "artifacts"),
        story="the run after a label changed",
    )

    world.label_a_sample("SNARE", rating=4)
    runner.run(Run(), SETTLED, story="the run after only a rating changed")


def test_a_descriptor_that_ended_a_success_without_finishing_stops_the_run(runner: ScenarioRunner) -> None:
    runner.run(
        Run(faults=FaultPlan(steps={"descriptor": StepFault(effect=ScriptedEffect.NO_OUTPUT)})),
        BUILT.stopped_at("descriptor", AttemptOutcome.NO_OUTPUT, ExitStatus.FAILED, after=_after("descriptor")).moving(
            "modules", "samples", "relations", "files", "passes", "experiments", "suggestions", "artifacts"
        ),
        story="a run whose descriptor training leaves no finished model",
    )


def test_outputs_lost_or_changed_on_disk_are_built_sealed_or_published_again(
    runner: ScenarioRunner, world: World
) -> None:
    """A model built again into the same bytes needs no publishing; a published copy changed on disk does."""
    _built(runner)
    codec = world.library_root / "models" / f"{world.step_outputs('morph-codec')['artifact']}"
    restorer = world.library_root / "models" / f"{world.step_outputs('restorer')['artifact']}"
    sealed = world.library_root / "models" / "descriptors" / world.step_outputs("descriptor")["sealed"]

    codec.unlink()
    runner.run(Run(), SETTLED.with_steps(morph_codec=StepVerdict.RAN), story="the run after the codec was deleted")

    restorer.with_name(restorer.name + ".pipeline.json").unlink()
    runner.run(
        Run(),
        SETTLED.with_steps(restorer=StepVerdict.RESEALED).moving("artifacts"),
        story="the run after the restorer's sidecar went",
    )

    sealed.unlink()
    runner.run(
        Run(),
        SETTLED.with_steps(descriptor=StepVerdict.RESEALED).because(descriptor=frozenset({SEALED_COPY_MISSING})),
        story="the run after the sealed descriptor was deleted",
    )

    published_restorer_path(world.library_root).write_bytes(b"someone else's restorer")
    runner.run(
        Run(), SETTLED.with_steps(morph_models=StepVerdict.RAN), story="the run after the published restorer changed"
    )


def test_a_run_from_scratch_builds_the_same_library_again(runner: ScenarioRunner, world: World) -> None:
    _built(runner)
    stale = world.library_root / "runs" / "descriptor" / "descriptor-run-0000000000000000"
    stale.mkdir(parents=True)

    observation = runner.run(
        Run(from_scratch=True), BUILT.ending(reset=AttemptOutcome.COMPLETED), story="the run from scratch"
    )

    assert "scratch completed" in observation.kinds
    assert not stale.exists()


def test_the_morph_target_takes_only_what_the_morph_models_need(runner: ScenarioRunner) -> None:
    runner.run(
        Run(targets=("morph",)),
        Expect.completed(
            ("labels", "modules", "sample-files", "morph-codec", "restorer", "morph-models"), StepVerdict.RAN
        )
        .with_steps(labels=StepVerdict.SATISFIED)
        .moving("modules", "samples", "files", "passes", "artifacts"),
        story="a run of the morph target on an empty library",
    )


def test_the_machine_a_library_is_built_on_names_none_of_its_outputs(runner: ScenarioRunner, world: World) -> None:
    """Workers, the device and a ceiling reach the commands, and every output stands as it was built."""
    _built(runner)
    world.set_pipeline_table(
        'memory_cap = "none"\nworkers = 2\ndevice = "cpu"\n\n[pipeline.descriptor]\nepochs = 40\nmemory_cap = "none"\n'
    )

    host = runner.start(Run())
    runner.finish(host, SETTLED, story="the run on another machine's settings")
