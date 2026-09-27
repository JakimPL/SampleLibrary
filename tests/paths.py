from __future__ import annotations

from pathlib import Path
from typing import Final

REPOSITORY_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
TESTS_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "tests"
BUILD_DEV_LIBRARY_SCRIPT: Final[Path] = REPOSITORY_DIRECTORY / "scripts" / "build_dev_library.py"
CHECKED_COMMITS_SCRIPT: Final[Path] = REPOSITORY_DIRECTORY / "scripts" / "checked_commits.py"
PIPELINE_SOURCE_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "src" / "samplelibrary" / "pipeline"
PIPELINE_SCENARIOS_DIRECTORY: Final[Path] = TESTS_DIRECTORY / "samplelibrary" / "pipeline" / "scenarios"
STAND_IN_PIPELINE_SCRIPT: Final[Path] = TESTS_DIRECTORY / "samplelibrary" / "app" / "stand_in_pipeline.py"
