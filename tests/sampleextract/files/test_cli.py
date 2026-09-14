from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleextract.files.cli import main
from tests.sampleextract.files.conftest import MINIMUM_SAMPLE_FRAMES, SamplePack

PROGRAM = "samplelibrary files"


def _write_config(tmp_path: Path, database_url: str, *, sample_directories: tuple[Path, ...]) -> Path:
    config_path = tmp_path / "config.toml"
    listed = ", ".join(f'"{directory.as_posix()}"' for directory in sample_directories)
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{database_url}"\n'
        f"minimum_sample_frames = {MINIMUM_SAMPLE_FRAMES}\n"
        f"sample_directories = [{listed}]\n",
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def configured(
    tmp_path: Path, _database_url: str, sample_pack: SamplePack, monkeypatch: pytest.MonkeyPatch
) -> SamplePack:
    config_path = _write_config(tmp_path, _database_url, sample_directories=(sample_pack.directory,))
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))
    return sample_pack


def test_a_scan_reports_what_it_cataloged(
    connection: Connection, configured: SamplePack, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--workers", "1"], prog=PROGRAM)

    assert "Discovered 4 sample files: 3 cataloged, 0 unchanged, 1 shorter" in capsys.readouterr().out
    assert PostgresSampleFileRepository(connection).count() == 3


def test_pruning_after_a_scan_removes_a_file_that_is_gone(
    connection: Connection, configured: SamplePack, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--workers", "1"], prog=PROGRAM)
    configured.kick.unlink()

    main(["--workers", "1", "--prune"], prog=PROGRAM)

    assert "Pruned 1 sample file(s)" in capsys.readouterr().out
    assert PostgresSampleFileRepository(connection).count() == 2


def test_a_prune_refused_for_a_missing_directory_ends_the_command_with_one_message(
    connection: Connection,
    tmp_path: Path,
    _database_url: str,
    sample_pack: SamplePack,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    unplugged = tmp_path / "unplugged"
    config_path = _write_config(tmp_path, _database_url, sample_directories=(sample_pack.directory, unplugged))
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(config_path))

    with pytest.raises(SystemExit) as raised:
        main(["--workers", "1", "--prune"], prog=PROGRAM)

    assert raised.value.code == 1
    output = capsys.readouterr()
    assert f"The sample directory {unplugged} is not there" in output.err
    assert "Pruned nothing" in output.err
    assert PostgresSampleFileRepository(connection).count() == 3
