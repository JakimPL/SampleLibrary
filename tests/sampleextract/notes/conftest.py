from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.config import LibraryConfig


@pytest.fixture
def config(tmp_path: Path) -> LibraryConfig:
    source = tmp_path / "source"
    source.mkdir()
    return LibraryConfig(module_source_directory=source, library_root=tmp_path / "library", database_url="unused")
