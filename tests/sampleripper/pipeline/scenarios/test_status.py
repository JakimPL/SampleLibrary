from __future__ import annotations

import os
import subprocess
import sys

from samplecore.exit_status import ExitStatus
from tests.paths import REPOSITORY_DIRECTORY
from tests.sampleripper.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.sampleripper.pipeline.scenarios.harness.stories import CATALOG, FIRST_BUILD
from tests.sampleripper.pipeline.scenarios.harness.world import World

STATUS_TIMEOUT_SECONDS = 120


def test_status_says_what_each_step_would_do_and_leaves_nothing_behind(runner: ScenarioRunner, world: World) -> None:
    runner.run(Run(targets=CATALOG), FIRST_BUILD, story="the first run")
    runs = sorted(world.layout.runs.iterdir())
    before = world.catalog_digests()

    finished = subprocess.run(
        [sys.executable, "-m", "sampleripper", "--config", str(world.config), "pipeline", "status", "catalog"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_DIRECTORY,
        env={name: value for name, value in os.environ.items() if not name.startswith("SAMPLERIPPER_")},
        timeout=STATUS_TIMEOUT_SECONDS,
    )

    assert finished.returncode == ExitStatus.COMPLETED, finished.stderr
    assert "labels                 satisfied" in finished.stdout
    assert "notes                  runs" in finished.stdout
    assert sorted(world.layout.runs.iterdir()) == runs
    assert world.catalog_digests() == before
