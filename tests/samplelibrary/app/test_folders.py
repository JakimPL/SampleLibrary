from __future__ import annotations

from pathlib import Path

import pytest

from samplelibrary.app.folders import FolderUnreadableError, list_folder, places


def test_a_folder_lists_its_visible_folders_in_name_order_with_its_own_file_counts(tmp_path: Path) -> None:
    for name in ("Zebra", "alpha", ".hidden"):
        (tmp_path / name).mkdir()
    for name in ("song.xm", "tune.IT", "kick.wav", "snare.flac", "notes.txt"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "alpha" / "deep.mod").write_bytes(b"")

    listing = list_folder(tmp_path)

    assert [folder.name for folder in listing.folders] == ["alpha", "Zebra"]
    assert listing.module_files == 2
    assert listing.audio_files == 2
    assert listing.parent == str(tmp_path.parent)


def test_a_path_naming_no_folder_is_refused(tmp_path: Path) -> None:
    (tmp_path / "file.wav").write_bytes(b"")

    with pytest.raises(FolderUnreadableError):
        list_folder(tmp_path / "file.wav")
    with pytest.raises(FolderUnreadableError):
        list_folder(tmp_path / "missing")


def test_the_places_start_at_home_and_end_with_the_drives() -> None:
    listed = places()

    assert listed[0].path == str(Path.home())
    assert Path(listed[-1].path).is_dir()
