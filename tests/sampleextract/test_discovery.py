from __future__ import annotations

from pathlib import Path

from samplecore.models.tracker import TrackerFormat
from sampleextract.discovery import FORMAT_LOADERS, discover_modules


def test_format_loaders_names_exactly_xm_and_it() -> None:
    assert FORMAT_LOADERS == {".xm": TrackerFormat.XM, ".it": TrackerFormat.IT}


def test_discover_modules_finds_only_supported_extensions_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.xm").write_bytes(b"")
    (tmp_path / "a.it").write_bytes(b"")
    (tmp_path / "c.mod").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")

    discovered = discover_modules(tmp_path)

    assert discovered == (tmp_path / "a.it", tmp_path / "b.xm")


def test_discover_modules_is_case_insensitive_on_extension(tmp_path: Path) -> None:
    (tmp_path / "loud.XM").write_bytes(b"")

    assert discover_modules(tmp_path) == (tmp_path / "loud.XM",)


def test_discover_modules_walks_subdirectories(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "song.it").write_bytes(b"")

    assert discover_modules(tmp_path) == (nested / "song.it",)


def test_discover_modules_skips_directories_matching_the_suffix(tmp_path: Path) -> None:
    (tmp_path / "not-a-file.xm").mkdir()

    assert discover_modules(tmp_path) == ()
