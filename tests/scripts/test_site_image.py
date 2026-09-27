from __future__ import annotations

from pathlib import Path
from typing import Final

from samplecore.config import parse_config
from sampleserver.addresses import names_loopback
from sampleserver.policy import ServingPolicy
from tests.paths import REPOSITORY_DIRECTORY

SITE_CONFIG: Final[Path] = REPOSITORY_DIRECTORY / "docker" / "site.toml"


def test_the_image_serves_its_library_to_anyone_with_its_renderer_beside_it() -> None:
    config = parse_config(SITE_CONFIG.read_text(encoding="utf-8"), SITE_CONFIG)

    assert ServingPolicy.of(config.server).permits_site
    assert names_loopback(config.inference.host)
    assert config.database_urls() == {}
