from __future__ import annotations

from pathlib import Path

import pytest

from sampleripper.app.instance import place


@pytest.fixture(autouse=True)
def _instances_in_the_test_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the locks and records an application takes in the test's own folder."""
    monkeypatch.setattr(place, "instances_directory", lambda: tmp_path / "instances")
