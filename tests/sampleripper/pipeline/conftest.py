from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from sampledescriptor import pretrained
from sampledescriptor.geometry import Anchor
from sampledescriptor.pretrained import PretrainedGrid, PretrainedRelease, write_pretrained_release

PUBLISHED: Final[PretrainedRelease] = PretrainedRelease(
    url="https://example.com/descriptor.pt",
    sha256="ab" * 32,
    grid=PretrainedGrid(canonicalizer="log_frequency", anchor=Anchor.NONE, bands_per_semitone=3),
)


@pytest.fixture(name="published")
def fixture_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PretrainedRelease:
    """The installation's release record: the pipeline plans from it alone, before any download."""
    path = tmp_path / "pretrained.toml"
    write_pretrained_release(PUBLISHED, path)
    monkeypatch.setattr(pretrained, "PRETRAINED_RELEASE_PATH", path)
    return PUBLISHED


@pytest.fixture(name="unpublished")
def fixture_unpublished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An installation carrying no published descriptor, as a version released before one exists."""
    monkeypatch.setattr(pretrained, "PRETRAINED_RELEASE_PATH", tmp_path / "missing.toml")
