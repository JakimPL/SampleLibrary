from __future__ import annotations

import os
from pathlib import Path

import pytest

from samplecore.models.tracker import TrackerFormat
from sampleextract.discovery import FORMAT_LOADERS, discover_modules


def test_format_loaders_names_every_supported_format() -> None:
    assert FORMAT_LOADERS == {
        ".xm": TrackerFormat.XM,
        ".it": TrackerFormat.IT,
        ".mod": TrackerFormat.MOD,
        ".s3m": TrackerFormat.S3M,
    }


def test_discover_modules_finds_only_supported_extensions_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.xm").write_bytes(b"")
    (tmp_path / "a.it").write_bytes(b"")
    (tmp_path / "d.mod").write_bytes(b"")
    (tmp_path / "e.s3m").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")

    discovered = discover_modules(tmp_path)

    assert discovered.paths == (tmp_path / "a.it", tmp_path / "b.xm", tmp_path / "d.mod", tmp_path / "e.s3m")
    assert discovered.unreadable_directories == ()


def test_discover_modules_is_case_insensitive_on_extension(tmp_path: Path) -> None:
    (tmp_path / "loud.XM").write_bytes(b"")

    assert discover_modules(tmp_path).paths == (tmp_path / "loud.XM",)


def test_discover_modules_walks_subdirectories(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "song.it").write_bytes(b"")

    assert discover_modules(tmp_path).paths == (nested / "song.it",)


def test_discover_modules_skips_directories_matching_the_suffix(tmp_path: Path) -> None:
    (tmp_path / "not-a-file.xm").mkdir()

    assert discover_modules(tmp_path).paths == ()


def test_a_folder_linked_into_the_collection_is_walked_once_even_when_a_link_points_back_up(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "linked.xm").write_bytes(b"")
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "direct.it").write_bytes(b"")
    (collection / "drive").symlink_to(elsewhere, target_is_directory=True)
    (elsewhere / "back").symlink_to(collection, target_is_directory=True)

    discovered = discover_modules(collection)

    assert sorted(path.name for path in discovered.paths) == ["direct.it", "linked.xm"]


@pytest.mark.skipif(os.geteuid() == 0, reason="a superuser reads every folder")
def test_a_folder_that_cannot_be_listed_is_named(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        discovered = discover_modules(tmp_path)
    finally:
        locked.chmod(0o755)

    assert discovered.unreadable_directories == (locked,)


def test_a_missing_source_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        discover_modules(tmp_path / "unmounted")


def test_a_library_without_a_module_collection_discovers_no_modules() -> None:
    discovered = discover_modules(None)

    assert discovered.paths == ()
    assert discovered.unreadable_directories == ()
