from __future__ import annotations

from pathlib import Path

import pytest

from samplecore.config import DATABASE_URL_ENVIRONMENT_VARIABLE, ConfigurationError, load_config
from samplecore.config_editing import LibrarySources, write_library_sources


@pytest.fixture
def sources(tmp_path: Path) -> LibrarySources:
    return LibrarySources(
        library_root=tmp_path / "library",
        module_source_directory=tmp_path / "modules",
        sample_directories=(tmp_path / "packs",),
        sample_exclusions=("*loop*",),
    )


def test_sources_written_into_a_new_file_read_back_as_chosen(
    tmp_path: Path, sources: LibrarySources, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    path = tmp_path / "settings" / "config.toml"

    written = write_library_sources(path, sources)

    assert LibrarySources.of(written) == sources
    assert LibrarySources.of(load_config(path)) == sources
    assert written.manages_database


def test_writing_sources_keeps_every_other_setting_and_comment(tmp_path: Path, sources: LibrarySources) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "# Mine.\n"
        "[library]\n"
        f'library_root = "{(tmp_path / "old").as_posix()}"\n'
        "minimum_sample_frames = 1024\n"
        "[inference]\n"
        'url = "http://127.0.0.1:9000"\n',
        encoding="utf-8",
    )

    written = write_library_sources(path, sources)

    assert written.minimum_sample_frames == 1024
    assert written.inference.port == 9000
    assert path.read_text(encoding="utf-8").startswith("# Mine.\n")


def test_sources_left_empty_leave_their_settings_out(tmp_path: Path, sources: LibrarySources) -> None:
    path = tmp_path / "config.toml"
    write_library_sources(path, sources)
    emptied = sources.model_copy(
        update={"module_source_directory": None, "sample_directories": (), "sample_exclusions": ()}
    )

    written = write_library_sources(path, emptied)

    assert LibrarySources.of(written) == emptied
    content = path.read_text(encoding="utf-8")
    assert "module_source_directory" not in content
    assert "sample_directories" not in content


def test_sources_that_fail_validation_leave_the_file_as_it_was(tmp_path: Path, sources: LibrarySources) -> None:
    path = tmp_path / "config.toml"
    write_library_sources(path, sources)
    before = path.read_bytes()
    overlapping = sources.model_copy(update={"sample_directories": (tmp_path / "packs", tmp_path / "packs" / "drums")})

    with pytest.raises(ConfigurationError, match="overlap"):
        write_library_sources(path, overlapping)

    assert path.read_bytes() == before
