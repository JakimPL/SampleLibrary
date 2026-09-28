from __future__ import annotations

from pathlib import Path
from typing import Final

REPOSITORY_DIRECTORY: Final[Path] = Path(__file__).resolve().parents[1]
TESTS_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "tests"
SCRIPTS_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "scripts"
BUILD_DEV_LIBRARY_SCRIPT: Final[Path] = SCRIPTS_DIRECTORY / "build_dev_library.py"
RENDER_ICONS_SCRIPT: Final[Path] = SCRIPTS_DIRECTORY / "render_icons.py"
FAVICON: Final[Path] = REPOSITORY_DIRECTORY / "frontend" / "public" / "favicon.svg"
ICONS_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "frontend" / "public" / "icons"
CHECKED_COMMITS_SCRIPT: Final[Path] = REPOSITORY_DIRECTORY / "scripts" / "checked_commits.py"
PIPELINE_SOURCE_DIRECTORY: Final[Path] = REPOSITORY_DIRECTORY / "src" / "sampleripper" / "pipeline"
PIPELINE_SCENARIOS_DIRECTORY: Final[Path] = TESTS_DIRECTORY / "sampleripper" / "pipeline" / "scenarios"
STAND_IN_PIPELINE_SCRIPT: Final[Path] = TESTS_DIRECTORY / "sampleripper" / "app" / "stand_in_pipeline.py"
