from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

CHECKED_COMMITS_NAME: Final[str] = "samplelibrary-checked-commits"
CHECK_START_NAME: Final[str] = "samplelibrary-check-start"
KEPT_COMMITS: Final[int] = 500
PUSHED_COMMIT_VARIABLE: Final[str] = "PRE_COMMIT_TO_REF"
STEPS: Final[tuple[str, ...]] = ("start", "record", "verify")
RECORDED: Final[str] = "Commit {commit} passed every check and can be pushed."
CHANGED_FILES: Final[str] = (
    "Every check passed, but the files differ from the last commit, so no commit is marked as checked. "
    "Commit the changes and run `just check` again before pushing."
)
UNCHECKED: Final[str] = "The commit you're pushing hasn't passed `just check`. Run it, then push again."


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark the commit `just check` passed on, and let a push through for a marked commit alone."
    )
    parser.add_argument("step", choices=STEPS, help="start or record a check, or verify the commit a push sends.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Mark the commits every check passed on, so a push waits for no check while git holds the connection.

    `start` notes the commit `just check` begins on, and `record` marks it once every check passed,
    when the files were exactly that commit's from the start to the end. `verify`, which the
    pre-push hook runs, lets a push through when the commit it sends is marked. The marks live in
    the git folder of the repository the working directory is in.

    Raises:
        SystemExit: `verify` finds the pushed commit unmarked.
    """
    arguments = _parse_arguments(argv)
    match arguments.step:
        case "start":
            _start()
        case "record":
            _record()
        case "verify":
            _verify()


def _start() -> None:
    _git_file(CHECK_START_NAME).write_text(_clean_commit() or "", encoding="utf-8")


def _record() -> None:
    start_file = _git_file(CHECK_START_NAME)
    started_on = start_file.read_text(encoding="utf-8") if start_file.is_file() else ""
    start_file.unlink(missing_ok=True)
    commit = _clean_commit()
    if not started_on or commit != started_on:
        print(CHANGED_FILES, file=sys.stderr)
        return
    checked = [line for line in _checked_commits() if line != commit]
    checked.append(commit)
    _git_file(CHECKED_COMMITS_NAME).write_text("\n".join(checked[-KEPT_COMMITS:]) + "\n", encoding="utf-8")
    print(RECORDED.format(commit=commit[:12]))


def _verify() -> None:
    """Let the push through when the commit pre-commit names as pushed is marked; a deletion sends none.

    Raises:
        SystemExit: the pushed commit is unmarked.
    """
    commit = os.environ.get(PUSHED_COMMIT_VARIABLE)
    if commit and commit not in _checked_commits():
        sys.exit(UNCHECKED)


def _checked_commits() -> list[str]:
    path = _git_file(CHECKED_COMMITS_NAME)
    return path.read_text(encoding="utf-8").split() if path.is_file() else []


def _clean_commit() -> str | None:
    """The commit checked out, while the working tree holds exactly its files and nothing untracked."""
    if _git("status", "--porcelain", "--untracked-files=normal"):
        return None
    return _git("rev-parse", "HEAD")


def _git_file(name: str) -> Path:
    return Path(_git("rev-parse", "--git-path", name))


def _git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    main()
