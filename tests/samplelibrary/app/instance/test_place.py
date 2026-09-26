from __future__ import annotations

from pathlib import Path

import pytest

from samplelibrary.app.instance import place
from samplelibrary.app.instance.place import config_key, instance_place


def test_one_config_file_keeps_one_key_however_its_path_is_spelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "settings" / "config.toml"
    monkeypatch.chdir(tmp_path)

    assert config_key(Path("settings") / "config.toml") == config_key(config_path)
    assert config_key(config_path.parent / ".." / "settings" / "config.toml") == config_key(config_path)


def test_two_config_files_get_places_of_their_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(place, "instances_directory", lambda: tmp_path / "instances")

    first = instance_place(tmp_path / "first" / "config.toml")
    second = instance_place(tmp_path / "second" / "config.toml")

    assert first.directory != second.directory
    assert first.lock.parent == first.directory == tmp_path / "instances" / first.key
    assert first.record.parent == first.directory
