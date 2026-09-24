from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from samplecore.config import LibraryConfig
from samplelibrary.app.jobs import BuildTarget, JobAlreadyRunningError, JobRunner, JobStatus, JobView, StepState
from samplelibrary.pipeline.steps.library import library_graph

STAND_IN_PIPELINE: Final[tuple[str, ...]] = (sys.executable, str(Path(__file__).with_name("stand_in_pipeline.py")))
IDLE_PIPELINE: Final[tuple[str, ...]] = (sys.executable, "-c", "import time; time.sleep(60)")
FINISH_TIMEOUT_SECONDS: Final[float] = 30.0


@dataclass(frozen=True)
class BuildCase:
    target: BuildTarget
    status: JobStatus
    states: tuple[StepState, ...]


@pytest.fixture
def config(tmp_path: Path) -> LibraryConfig:
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\n', encoding="utf-8")
    return LibraryConfig(library_root=tmp_path / "library")


def _finished(runner: JobRunner) -> JobView:
    deadline = time.monotonic() + FINISH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        view = runner.view()
        if view is not None and view.status is not JobStatus.RUNNING:
            return view
        time.sleep(0.05)
    raise AssertionError("the build kept running")


@pytest.mark.parametrize(
    "case",
    [
        BuildCase(
            BuildTarget.CATALOG, JobStatus.COMPLETED, (StepState.UP_TO_DATE, StepState.DONE, StepState.UP_TO_DATE)
        ),
        BuildCase(BuildTarget.ALL, JobStatus.FAILED, (StepState.UP_TO_DATE, StepState.FAILED, StepState.SKIPPED)),
    ],
    ids=lambda case: case.target.value,
)
def test_a_build_reports_each_step_as_the_run_recorded_it(
    tmp_path: Path, config: LibraryConfig, case: BuildCase
) -> None:
    runner = JobRunner(config_path=tmp_path / "config.toml", pipeline_command=STAND_IN_PIPELINE)

    runner.start(config, case.target)
    view = _finished(runner)

    assert view.status is case.status
    assert tuple(step.state for step in view.steps) == case.states
    assert view.steps[1].progress is not None
    assert view.steps[1].progress.done == 7


def test_a_failed_build_names_the_step_and_shows_the_end_of_its_log(tmp_path: Path, config: LibraryConfig) -> None:
    runner = JobRunner(config_path=tmp_path / "config.toml", pipeline_command=STAND_IN_PIPELINE)

    runner.start(config, BuildTarget.ALL)
    view = _finished(runner)

    assert view.problem is not None and "thumbnails" in view.problem
    assert view.log_tail[-1] == "the disk is full"


def test_one_build_runs_at_a_time_and_a_canceled_one_says_so(tmp_path: Path, config: LibraryConfig) -> None:
    runner = JobRunner(config_path=tmp_path / "config.toml", pipeline_command=IDLE_PIPELINE)
    runner.start(config, BuildTarget.CATALOG)

    with pytest.raises(JobAlreadyRunningError):
        runner.start(config, BuildTarget.CATALOG)
    runner.stop()

    view = runner.view()
    assert view is not None and view.status is JobStatus.CANCELED


@pytest.mark.parametrize("target", list(BuildTarget))
def test_every_build_target_is_one_the_pipeline_knows(target: BuildTarget) -> None:
    library_graph().order((target.value,))
