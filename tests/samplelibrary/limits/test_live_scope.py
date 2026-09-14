from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.exit_status import ExitStatus
from samplelibrary.limits.systemd import PROBE_TIMEOUT_SECONDS, SYSTEMD_RUN

RUN_TIMEOUT_SECONDS = 120


def _user_scopes_enforce_a_ceiling() -> bool:
    """Whether this session runs a user manager that opens scopes, which is what holds a ceiling here."""
    if sys.platform == "win32":
        return False
    try:
        probe = subprocess.run(
            [SYSTEM_RUN, "--user", "--scope", "--quiet", "--collect", "--", "true"],
            check=False,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


SYSTEM_RUN = SYSTEMD_RUN
pytestmark = pytest.mark.skipif(
    not _user_scopes_enforce_a_ceiling(), reason="this session runs no user manager that opens systemd scopes"
)


@pytest.fixture(name="library_config")
def fixture_library_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{tmp_path.as_posix()}"\n'
        f'library_root = "{tmp_path.as_posix()}"\n'
        'database_url = "postgresql+psycopg://unused@localhost:1/unused"\n',
        encoding="utf-8",
    )
    return config_path


def _capped_run(library_config: Path, ceiling: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "samplelibrary",
            "--config",
            str(library_config),
            "--memory-cap",
            ceiling,
            "--memory-scope",
            f"samplelibrary-test-{uuid.uuid4().hex[:12]}",
            "tracking",
            "uri",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
        env={**_clean_environment(), CONFIG_PATH_ENVIRONMENT_VARIABLE: str(library_config)},
    )


def _clean_environment() -> dict[str, str]:
    import os  # pylint: disable=import-outside-toplevel

    return {name: value for name, value in os.environ.items() if not name.startswith("SAMPLELIBRARY_")}


def test_a_command_under_a_ceiling_it_stays_within_runs_and_reports_what_it_held(library_config: Path) -> None:
    finished = _capped_run(library_config, "512M")

    assert finished.returncode == ExitStatus.COMPLETED, finished.stderr
    assert "mlflow.db" in finished.stdout
    assert "Held at most" in finished.stdout


def test_a_command_that_cannot_fit_its_ceiling_is_stopped_by_the_kernel(library_config: Path) -> None:
    """The kernel stops a run that outgrows its ceiling, which is what keeps a long pass from taking the machine down."""
    finished = _capped_run(library_config, "8M")

    assert finished.returncode != ExitStatus.COMPLETED
    assert finished.returncode in (-9, 137, ExitStatus.MEMORY_CAP_REACHED, ExitStatus.FAILED)
    assert "mlflow.db" not in finished.stdout
