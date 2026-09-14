from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.models.sample_file import SampleFileLocation
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from samplecore.storage.sample_audio import SampleAudio
from sampleextract.files import run as run_module
from sampleextract.files.discovery import discover_sample_files
from sampleextract.files.run import SampleFileScanSummary, scan_sample_files
from sampleextract.parsing import FailureStage
from tests.sampleextract.conftest import CountingProgress
from tests.sampleextract.files.conftest import RATE, SamplePack


def _scan(config: LibraryConfig, connection: Connection, progress: CountingProgress) -> SampleFileScanSummary:
    discovery = discover_sample_files(config.sample_directories, exclusions=config.sample_exclusions)
    return scan_sample_files(config, connection, discovery.locations, progress=progress)


def _location(sample_pack: SamplePack, path: Path) -> SampleFileLocation:
    return SampleFileLocation(
        directory=sample_pack.directory, relative_path=path.relative_to(sample_pack.directory).as_posix()
    )


def test_a_scan_catalogs_each_file_in_place_with_its_sample_and_thumbnail(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, progress: CountingProgress
) -> None:
    summary = _scan(files_config, connection, progress)

    assert (summary.discovered, summary.cataloged, summary.too_short, summary.failures) == (4, 3, 1, ())
    assert progress.advanced == 4
    sample_files = PostgresSampleFileRepository(connection).list_all()
    assert {sample_file.location for sample_file in sample_files} == summary.present_locations
    kick = decode_sample_file(sample_pack.kick).sample_pcm
    assert PostgresSampleRepository(connection).get(kick.sample.hash) == kick.sample
    assert PostgresSampleThumbnailRepository(connection).get(kick.sample.hash) is not None
    assert all(sample_file.rate == RATE for sample_file in sample_files)
    read = SampleAudio.from_catalog(connection, files_config.library_root).read(kick.sample)
    assert np.array_equal(read.pcm, kick.pcm)
    assert not (files_config.library_root / "objects").exists()


def test_a_repeat_scan_leaves_unchanged_cataloged_files_unread(
    connection: Connection,
    files_config: LibraryConfig,
    sample_pack: SamplePack,
    progress: CountingProgress,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_pack.too_short.unlink()
    first = _scan(files_config, connection, progress)

    def refuse_to_decode(path: Path) -> None:
        raise AssertionError(f"{path} was decoded again")

    monkeypatch.setattr(run_module, "decode_sample_file", refuse_to_decode)
    repeat = _scan(files_config, connection, progress)

    assert (repeat.cataloged, repeat.unchanged) == (0, 3)
    assert repeat.present_locations == first.present_locations


def test_a_file_written_again_is_cataloged_under_what_it_holds_now(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, progress: CountingProgress
) -> None:
    _scan(files_config, connection, progress)
    soundfile.write(sample_pack.kick, np.linspace(-0.5, 0.5, 2048), RATE, subtype="PCM_16")

    summary = _scan(files_config, connection, progress)

    assert summary.cataloged == 1
    cataloged = PostgresSampleFileRepository(connection).get(_location(sample_pack, sample_pack.kick))
    assert cataloged is not None
    assert cataloged.sample_hash == decode_sample_file(sample_pack.kick).sample_pcm.sample.hash


def test_two_files_holding_one_sound_share_one_sample(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, progress: CountingProgress
) -> None:
    copy = sample_pack.directory / "Kicks" / "Kick 01 copy.wav"
    copy.write_bytes(sample_pack.kick.read_bytes())

    _scan(files_config, connection, progress)

    kick_hash = decode_sample_file(sample_pack.kick).sample_pcm.sample.hash
    holding = PostgresSampleFileRepository(connection).list_for_samples([kick_hash])
    assert [sample_file.location.stem for sample_file in holding] == ["Kick 01 copy", "Kick 01"]


def test_a_file_that_fails_to_decode_is_a_failure_that_stays_present(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, progress: CountingProgress
) -> None:
    broken = sample_pack.directory / "Kicks" / "Broken.wav"
    broken.write_bytes(b"RIFF but nothing a decoder recognizes")

    summary = _scan(files_config, connection, progress)

    assert [(failure.path, failure.stage) for failure in summary.failures] == [(broken, FailureStage.DECODE)]
    assert _location(sample_pack, broken) in summary.present_locations


def test_a_file_that_cannot_be_read_is_a_read_failure(
    connection: Connection, files_config: LibraryConfig, sample_pack: SamplePack, progress: CountingProgress
) -> None:
    sample_pack.loop.chmod(0)
    try:
        summary = _scan(files_config, connection, progress)
    finally:
        sample_pack.loop.chmod(0o644)

    assert [(failure.path, failure.stage) for failure in summary.failures] == [(sample_pack.loop, FailureStage.READ)]
    assert _location(sample_pack, sample_pack.loop) not in summary.present_locations
