from __future__ import annotations

import stat
from pathlib import Path

import pytest

from samplecore.config import DATABASE_URL_ENVIRONMENT_VARIABLE, ConfigurationError, load_config
from samplecore.config_editing import LibraryOptions, LibrarySources, write_library_options, write_library_sources
from samplecore.storage.atomic import PRIVATE_FILE_MODE


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
    assert 'exposure = "local"' in path.read_text(encoding="utf-8")


def test_a_rewritten_config_stays_readable_by_its_owner_alone(tmp_path: Path, sources: LibrarySources) -> None:
    """Its database URLs hold passwords."""
    path = tmp_path / "config.toml"
    path.write_text(f'[library]\nlibrary_root = "{(tmp_path / "library").as_posix()}"\n', encoding="utf-8")
    path.chmod(0o644)

    write_library_sources(path, sources)
    after_sources = stat.S_IMODE(path.stat().st_mode)
    write_library_options(path, LibraryOptions(build_cloud=True, open_to_network=False))

    assert after_sources == stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


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


def test_options_written_beside_the_sources_leave_them_as_chosen(
    tmp_path: Path, sources: LibrarySources, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    path = tmp_path / "config.toml"
    write_library_sources(path, sources)

    chosen = LibraryOptions(build_cloud=False, open_to_network=True)

    written = write_library_options(path, chosen)

    assert LibraryOptions.of(load_config(path)) == LibraryOptions.of(written) == chosen
    assert LibrarySources.of(load_config(path)) == sources


def test_a_library_opened_to_the_network_closes_again(tmp_path: Path, sources: LibrarySources) -> None:
    path = tmp_path / "config.toml"
    write_library_sources(path, sources)
    write_library_options(path, LibraryOptions(build_cloud=True, open_to_network=True))

    written = write_library_options(path, LibraryOptions(build_cloud=True, open_to_network=False))

    assert not written.server.answers_the_home_network
    assert not load_config(path).server.answers_the_home_network
