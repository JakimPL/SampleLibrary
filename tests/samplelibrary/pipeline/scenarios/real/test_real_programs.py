from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import Connection

from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.world import World, WorldSetup
from tests.samplelibrary.pipeline.scenarios.test_building import BUILT, EVERYTHING, SETTLED

# Every model is as small as its command allows, on the processor, so the real programs build the
# tiny world in minutes on a machine holding the listening model in its local cache.
TINY_PIPELINE_TABLE: Final[str] = (
    'memory_cap = "none"\nworkers = 1\ndevice = "cpu"\n'
    "\n[pipeline.grid-cache]\nviews = 1\n"
    "\n[pipeline.descriptor]\nepochs = 1\nbatch = 4\nwidth = 8\nlabeled_per_batch = 1\n"
    "\n[pipeline.evaluation]\nprobes = 4\n"
    "\n[pipeline.module-evaluation]\nprobes = 4\n"
    "\n[pipeline.morph-codec]\nlatent_size = 2\nsamples = 8\n"
    "\n[pipeline.restorer]\nepochs = 1\nbatch = 2\nchannels = 8\ncrop = 16\n"
)
ADDED_PACK_FILES: Final[int] = 6

pytestmark = pytest.mark.pipeline_real


@pytest.fixture(name="real_runner")
def fixture_real_runner(
    tmp_path: Path, _database_url: str, connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ScenarioRunner]:
    """A world whose every step runs its real program, reading the listening model from the local cache alone."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    world = World(
        root=tmp_path / "world",
        database_url=_database_url,
        connection=connection,
        setup=WorldSetup(pipeline_table=TINY_PIPELINE_TABLE),
    )
    world.build()
    for _ in range(ADDED_PACK_FILES):
        world.add_pack_file()
    runner = ScenarioRunner(world=world, stands_in=False)
    yield runner
    runner.close()
    world.close()


def test_the_real_programs_build_the_whole_library_and_find_it_built_again(real_runner: ScenarioRunner) -> None:
    real_runner.run(Run(), BUILT.moving(*EVERYTHING), story="the first run of the real programs")

    real_runner.run(Run(), SETTLED, story="the run after it")


def test_the_real_programs_take_in_a_sample_file_added_after_the_first_run(real_runner: ScenarioRunner) -> None:
    real_runner.run(Run(), BUILT.moving(*EVERYTHING), story="the first run of the real programs")
    real_runner.world.add_pack_file()

    real_runner.run(
        Run(),
        BUILT.moving("samples", "files", "passes", "experiments", "suggestions", "cloud", "artifacts"),
        story="the run after a sample file arrived",
    )
