from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pytest
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import pitched_keymap
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.songs.song import Song

from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from sampleextract import ingest as ingest_module_under_test
from sampleextract.ingest import ingest_module

MODULE_HASH = "d" * 64
SAMPLE_RATE = 44100
SongBuilder = Callable[[tuple[TrackModSample, ...], tuple[Instrument, ...]], Song]


def _two_instrument_song(builder: SongBuilder) -> Song:
    """Two instruments, each reaching one sample of its own, plus one sample no keymap reaches."""
    samples = (
        TrackModSample(name="lead", pcm=np.linspace(-1.0, 1.0, 16), rate=SAMPLE_RATE),
        TrackModSample(name="bass", pcm=np.linspace(1.0, -1.0, 24), rate=SAMPLE_RATE),
        TrackModSample(name="unreachable", pcm=np.zeros(8), rate=SAMPLE_RATE),
    )
    instruments = (
        Instrument(name="piano", keymap=pitched_keymap(sample=0)),
        Instrument(name="synth", keymap=pitched_keymap(sample=1)),
    )
    return builder(samples, instruments)


def _ingest_two_instrument_song(
    connection: duckdb.DuckDBPyConnection, library_root: Path, song_builder: SongBuilder
) -> None:
    ingest_module(
        connection,
        library_root,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=_two_instrument_song(song_builder),
        ingested_at=datetime.now(UTC),
    )


def test_ingest_module_returns_the_module_it_persisted(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    module = ingest_module(
        connection,
        tmp_path,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=_two_instrument_song(song_builder),
        ingested_at=datetime.now(UTC),
    )

    assert DuckDBModuleRepository(connection).get(MODULE_HASH) == module
    assert module.instrument_count == 2
    assert module.sample_count == 3


def test_ingest_module_only_stores_occurrences_a_keymap_reaches(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    properties = DuckDBSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)

    assert len(properties) == 2
    assert {item.occurrence.instrument_index for item in properties} == {0, 1}
    assert {item.occurrence.sample_slot for item in properties} == {0}


def test_ingest_module_writes_audio_a_stored_sample_can_be_read_back(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    properties = DuckDBSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)
    stored_sample = DuckDBSampleRepository(connection).get(properties[0].sample_hash)
    assert stored_sample is not None

    sample_pcm = audio_store.read(tmp_path, stored_sample)

    assert sample_pcm.pcm.shape == (stored_sample.frames, stored_sample.channels.value)


def test_ingest_module_a_second_time_for_the_same_hash_raises(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    with pytest.raises(duckdb.Error):
        _ingest_two_instrument_song(connection, tmp_path, song_builder)


def test_ingest_module_skips_a_reachable_placeholder_sample_with_no_frames(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    samples = (TrackModSample(name="placeholder", pcm=np.zeros(0), rate=SAMPLE_RATE),)
    instruments = (Instrument(name="empty", keymap=pitched_keymap(sample=0)),)

    ingest_module(
        connection,
        tmp_path,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=song_builder(samples, instruments),
        ingested_at=datetime.now(UTC),
    )

    assert DuckDBSamplePropertiesRepository(connection).list_for_module(MODULE_HASH) == ()


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, song_builder: SongBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _failing_write(*_: object, **__: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(ingest_module_under_test.audio_store, "write", _failing_write)

    with pytest.raises(OSError):
        _ingest_two_instrument_song(connection, tmp_path, song_builder)

    assert DuckDBModuleRepository(connection).get(MODULE_HASH) is None
    assert connection.execute("SELECT count(*) FROM sample_properties").fetchone() == (0,)
