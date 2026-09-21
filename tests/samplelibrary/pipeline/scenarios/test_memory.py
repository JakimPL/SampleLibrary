from __future__ import annotations

import subprocess
import sys

import pytest

from samplecore.exit_status import ExitStatus
from samplelibrary.limits.systemd import PROBE_TIMEOUT_SECONDS, SYSTEMD_RUN
from samplelibrary.pipeline.results import AttemptOutcome
from tests.samplelibrary.pipeline.scenarios.harness.observe import ledger_entries
from tests.samplelibrary.pipeline.scenarios.harness.plans import ScriptedEffect, StepFault
from tests.samplelibrary.pipeline.scenarios.harness.runner import Run, ScenarioRunner
from tests.samplelibrary.pipeline.scenarios.harness.stories import BUILT, CATALOG, CATALOG_PASSES, after, scripted
from tests.samplelibrary.pipeline.scenarios.harness.world import DEFAULT_PIPELINE_TABLE, World


def _user_scopes_enforce_a_ceiling() -> bool:
    if sys.platform == "win32":
        return False
    try:
        probe = subprocess.run(
            [SYSTEMD_RUN, "--user", "--scope", "--quiet", "--collect", "--", "true"],
            check=False,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = [
    pytest.mark.skipif(
        not _user_scopes_enforce_a_ceiling(), reason="this session runs no user manager that opens systemd scopes"
    ),
    pytest.mark.xdist_group("memory"),
]


def test_a_ceiling_named_for_one_step_holds_that_step_alone(runner: ScenarioRunner, world: World) -> None:
    world.set_pipeline_table(f'{DEFAULT_PIPELINE_TABLE}\n[pipeline.notes]\nmemory_cap = "2G"\n')
    host = runner.start(Run(targets=CATALOG, faults=scripted()))

    runner.finish(host, BUILT, story="a run holding notes to a ceiling of its own")

    ceilings = {str(entry["step"]): str(entry["memory_cap"]) for entry in ledger_entries(host.ledger)}
    assert ceilings == {step: "2G" if step == "notes" else "none" for step in CATALOG_PASSES}


def test_a_step_outgrowing_its_ceiling_is_stopped_and_ends_the_run_as_one(runner: ScenarioRunner, world: World) -> None:
    world.set_pipeline_table(f'{DEFAULT_PIPELINE_TABLE}\n[pipeline.thumbnails]\nmemory_cap = "256M"\n')

    runner.run(
        Run(targets=CATALOG, faults=scripted(thumbnails=StepFault(effect=ScriptedEffect.EXCEED_MEMORY))),
        BUILT.stopped_at(
            "thumbnails", AttemptOutcome.MEMORY_CAP_REACHED, ExitStatus.MEMORY_CAP_REACHED, after=after("thumbnails")
        ),
        story="a run whose thumbnails outgrow a 256M ceiling",
    )
