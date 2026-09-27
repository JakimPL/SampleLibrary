from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from tests.paths import CHECKED_COMMITS_SCRIPT

PUSHED_COMMIT_VARIABLE: Final[str] = "PRE_COMMIT_TO_REF"
GIT_IDENTITY: Final[dict[str, str]] = {
    "GIT_AUTHOR_NAME": "Tester",
    "GIT_AUTHOR_EMAIL": "tester@example.com",
    "GIT_COMMITTER_NAME": "Tester",
    "GIT_COMMITTER_EMAIL": "tester@example.com",
}


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_IDENTITY},
    ).stdout.strip()


def _step(repository: Path, step: str, *, pushed: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if name != PUSHED_COMMIT_VARIABLE}
    if pushed is not None:
        environment[PUSHED_COMMIT_VARIABLE] = pushed
    return subprocess.run(
        [sys.executable, str(CHECKED_COMMITS_SCRIPT), step],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A repository holding one commit, its working tree exactly that commit's files."""
    _git(tmp_path, "init", "--quiet")
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "module.py")
    _git(tmp_path, "commit", "--quiet", "--message", "Added: a module")
    return tmp_path


def test_a_commit_the_check_passed_on_is_let_through(repository: Path) -> None:
    commit = _git(repository, "rev-parse", "HEAD")

    _step(repository, "start")
    _step(repository, "record")

    assert _step(repository, "verify", pushed=commit).returncode == 0


def test_a_commit_no_check_passed_on_is_held_back(repository: Path) -> None:
    commit = _git(repository, "rev-parse", "HEAD")

    refused = _step(repository, "verify", pushed=commit)

    assert refused.returncode == 1
    assert "just check" in refused.stderr


@pytest.mark.parametrize("changed_at", ["start", "record"])
def test_a_check_over_files_the_commit_lacks_marks_no_commit(repository: Path, changed_at: str) -> None:
    commit = _git(repository, "rev-parse", "HEAD")
    if changed_at == "start":
        (repository / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    _step(repository, "start")
    (repository / "untracked.py").write_text("VALUE = 3\n", encoding="utf-8")

    recorded = _step(repository, "record")

    assert "no commit is marked" in recorded.stderr
    assert _step(repository, "verify", pushed=commit).returncode == 1


def test_a_push_sending_no_commit_is_let_through(repository: Path) -> None:
    assert _step(repository, "verify").returncode == 0
