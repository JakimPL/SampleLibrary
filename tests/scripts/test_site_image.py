from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

from samplecore.config import parse_config
from sampleserver.addresses import names_loopback
from sampleserver.policy import ServingPolicy
from tests.paths import REPOSITORY_DIRECTORY

DOCKERFILE: Final[Path] = REPOSITORY_DIRECTORY / "Dockerfile"
SITE_CONFIG: Final[Path] = REPOSITORY_DIRECTORY / "docker" / "site.toml"
TRACKMOD_SOURCE: Final[re.Pattern[str]] = re.compile(
    r"^ADD https://github\.com/JakimPL/TrackMod\.git#([0-9a-f]{40}) trackmod$", re.M
)


def test_the_image_builds_the_trackmod_the_submodule_names() -> None:
    """A platform building from the repository checks out no submodule, so the image names the commit itself."""
    staged = subprocess.run(
        ["git", "ls-files", "--stage", "trackmod"], cwd=REPOSITORY_DIRECTORY, capture_output=True, text=True, check=True
    ).stdout.split()
    match = TRACKMOD_SOURCE.search(DOCKERFILE.read_text(encoding="utf-8"))

    assert match is not None
    assert match.group(1) == staged[1]


def test_the_image_serves_its_library_to_anyone_with_its_renderer_beside_it() -> None:
    config = parse_config(SITE_CONFIG.read_text(encoding="utf-8"), SITE_CONFIG)

    assert ServingPolicy.of(config.server).permits_site
    assert names_loopback(config.inference.host)
    assert config.database_urls() == {}
