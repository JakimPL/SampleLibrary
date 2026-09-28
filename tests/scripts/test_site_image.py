from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.config import parse_config
from sampleserver.addresses import names_loopback
from sampleserver.policy import ServingPolicy
from tests.paths import REPOSITORY_DIRECTORY

SITE_CONFIG: Final[Path] = REPOSITORY_DIRECTORY / "docker" / "site.toml"
DOCKERFILE: Final[Path] = REPOSITORY_DIRECTORY / "Dockerfile"


def test_the_image_serves_its_library_to_anyone_with_its_renderer_beside_it() -> None:
    config = parse_config(SITE_CONFIG.read_text(encoding="utf-8"), SITE_CONFIG)

    assert ServingPolicy.of(config.server).permits_site
    assert names_loopback(config.inference.host)
    assert config.database_urls() == {}


def test_the_images_web_app_is_built_beside_the_project_file_it_reads_its_version_from() -> None:
    """The frontend stage copies the frontend folder alone, so the project file has to be put beside it as in a checkout."""
    frontend_stage = DOCKERFILE.read_text(encoding="utf-8").split("FROM ")[1]

    assert frontend_stage.index("COPY pyproject.toml /pyproject.toml") < frontend_stage.index("RUN npm run build")
