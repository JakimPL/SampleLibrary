from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import pitched_keymap
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.songs.song import Song

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.database import connect, sample_properties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from samplecore.waveform import DEFAULT_THUMBNAIL_BUCKET_COUNT, compute_waveform_peaks
from sampleextract import ingest as ingest_module_under_test
from sampleextract.ingest import ingest_module

MODULE_HASH = "d" * 64
SAMPLE_RATE = 44100
NO_MINIMUM_FRAMES = 1
CONCURRENT_INGEST_COUNT = 2
BARRIER_TIMEOUT_SECONDS = 30
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


def _ingest_two_instrument_song(connection: Connection, library_root: Path, song_builder: SongBuilder) -> None:
    ingest_module(
        connection,
        library_root,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=_two_instrument_song(song_builder),
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=NO_MINIMUM_FRAMES,
    )


def test_ingest_module_returns_the_module_it_persisted(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
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
        minimum_sample_frames=NO_MINIMUM_FRAMES,
    )

    assert PostgresModuleRepository(connection).get(MODULE_HASH) == module
    assert module.instrument_count == 2
    assert module.sample_count == 3


def test_ingest_module_only_stores_occurrences_a_keymap_reaches(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    properties = PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)

    assert len(properties) == 2
    assert {item.occurrence.instrument_index for item in properties} == {0, 1}
    assert {item.occurrence.sample_slot for item in properties} == {0}


def test_ingest_module_writes_audio_a_stored_sample_can_be_read_back(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    properties = PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)
    stored_sample = PostgresSampleRepository(connection).get(properties[0].sample_hash)
    assert stored_sample is not None

    sample_pcm = audio_store.read(tmp_path, stored_sample)

    assert sample_pcm.pcm.shape == (stored_sample.frames, stored_sample.channels.value)


def test_ingest_module_a_second_time_for_the_same_hash_raises(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    _ingest_two_instrument_song(connection, tmp_path, song_builder)

    with pytest.raises(IntegrityError):
        _ingest_two_instrument_song(connection, tmp_path, song_builder)


def test_ingest_module_skips_a_reachable_placeholder_sample_with_no_frames(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
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
        minimum_sample_frames=NO_MINIMUM_FRAMES,
    )

    assert PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH) == ()


def test_ingest_module_skips_a_reachable_sample_shorter_than_the_configured_minimum(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    samples = (TrackModSample(name="chiptune blip", pcm=np.linspace(-1.0, 1.0, 16), rate=SAMPLE_RATE),)
    instruments = (Instrument(name="blip", keymap=pitched_keymap(sample=0)),)

    ingest_module(
        connection,
        tmp_path,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=song_builder(samples, instruments),
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=32,
    )

    assert PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH) == ()
    assert PostgresSampleRepository(connection).list_all() == ()


def test_ingest_module_keeps_a_reachable_sample_at_or_above_the_configured_minimum(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    samples = (TrackModSample(name="kick", pcm=np.linspace(-1.0, 1.0, 32), rate=SAMPLE_RATE),)
    instruments = (Instrument(name="kick", keymap=pitched_keymap(sample=0)),)

    ingest_module(
        connection,
        tmp_path,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=song_builder(samples, instruments),
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=32,
    )

    assert len(PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)) == 1


def test_ingest_module_caches_a_thumbnail_matching_the_stored_sample_s_own_waveform(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder
) -> None:
    # The thumbnail is compared against this exact in-memory waveform, not a disk round trip
    # through the stored WAV: quantizing and dequantizing an 8/16-bit file introduces noise a
    # bit-for-bit comparison would wrongly flag, the same reasoning `compute_waveform_peaks`'s own
    # bit-depth-independence already rests on.
    pcm = np.linspace(-1.0, 1.0, 32)
    samples = (TrackModSample(name="kick", pcm=pcm, rate=SAMPLE_RATE),)
    instruments = (Instrument(name="kick", keymap=pitched_keymap(sample=0)),)

    ingest_module(
        connection,
        tmp_path,
        module_hash=MODULE_HASH,
        tracker=TrackerFormat.XM,
        filename="song.xm",
        file_size=4096,
        song=song_builder(samples, instruments),
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=NO_MINIMUM_FRAMES,
    )

    properties = PostgresSamplePropertiesRepository(connection).list_for_module(MODULE_HASH)
    thumbnail = PostgresSampleThumbnailRepository(connection).get(properties[0].sample_hash)
    assert thumbnail is not None

    expected_peaks = compute_waveform_peaks(pcm.reshape(-1, 1), bucket_count=DEFAULT_THUMBNAIL_BUCKET_COUNT)
    assert thumbnail.bucket_count == len(expected_peaks)
    assert thumbnail.minimums == tuple(peak.minimum for peak in expected_peaks)
    assert thumbnail.maximums == tuple(peak.maximum for peak in expected_peaks)


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _failing_write(*_: object, **__: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(ingest_module_under_test.audio_store, "write", _failing_write)

    with pytest.raises(OSError):
        _ingest_two_instrument_song(connection, tmp_path, song_builder)

    assert PostgresModuleRepository(connection).get(MODULE_HASH) is None
    assert connection.execute(select(func.count()).select_from(sample_properties)).scalar_one() == 0


class _FirstWriteBarrier:
    """Holds every thread until each has reached its first sample, before any of them takes a row.

    Waiting at the point a waveform is rendered, ahead of the row it is about to claim, is what lets
    both transactions arrive: a thread that already held one shared row would keep the other waiting
    somewhere earlier and never reach the barrier at all.
    """

    def __init__(self, parties: int) -> None:
        self._barrier = threading.Barrier(parties, timeout=BARRIER_TIMEOUT_SECONDS)
        self._lock = threading.Lock()
        self._arrived: set[int] = set()

    def reached(self) -> None:
        thread = threading.get_ident()
        with self._lock:
            first_time = thread not in self._arrived
            self._arrived.add(thread)

        if first_time:
            self._barrier.wait()


def _sample_hash_of(trackmod_sample: TrackModSample) -> str:
    return compute_sample_hash(
        depth=trackmod_sample.depth,
        channels=ChannelLayout(trackmod_sample.channels),
        frames=trackmod_sample.frames,
        pcm=trackmod_sample.pcm,
    )


def _pair_ordered_against_their_hashes() -> tuple[TrackModSample, TrackModSample]:
    """Two samples in slot order, the higher content hash first, so slot order opposes hash order."""
    first = TrackModSample(name="lead", pcm=np.linspace(-1.0, 1.0, 64), rate=SAMPLE_RATE)
    second = TrackModSample(name="bass", pcm=np.linspace(1.0, -1.0, 96), rate=SAMPLE_RATE)
    return (first, second) if _sample_hash_of(first) > _sample_hash_of(second) else (second, first)


def _two_pitched_instruments() -> tuple[Instrument, ...]:
    return (
        Instrument(name="one", keymap=pitched_keymap(sample=0)),
        Instrument(name="two", keymap=pitched_keymap(sample=1)),
    )


def _ingest_pair(
    connection: Connection,
    library_root: Path,
    song_builder: SongBuilder,
    *,
    module_hash: str,
    samples: tuple[TrackModSample, ...],
) -> None:
    ingest_module(
        connection,
        library_root,
        module_hash=module_hash,
        tracker=TrackerFormat.XM,
        filename=f"{module_hash[:8]}.xm",
        file_size=4096,
        song=song_builder(samples, _two_pitched_instruments()),
        ingested_at=datetime.now(UTC),
        minimum_sample_frames=NO_MINIMUM_FRAMES,
    )


def test_the_rows_two_modules_share_are_written_in_ascending_hash_order(
    connection: Connection, tmp_path: Path, song_builder: SongBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hash order is the total order concurrent ingests agree on, whichever slots a module holds."""
    written: list[str] = []
    render = ingest_module_under_test.render_sample_pcm

    def record(sample_hash: str, trackmod_sample: TrackModSample) -> SamplePCM:
        written.append(sample_hash)
        return render(sample_hash, trackmod_sample)

    monkeypatch.setattr(ingest_module_under_test, "render_sample_pcm", record)

    _ingest_pair(
        connection, tmp_path, song_builder, module_hash=MODULE_HASH, samples=_pair_ordered_against_their_hashes()
    )

    assert len(written) == 2
    assert written == sorted(written)


def test_two_modules_holding_one_pair_in_opposite_slots_both_commit(
    connection: Connection,
    _database_url: str,
    tmp_path: Path,
    song_builder: SongBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two runs reaching one pair of samples at once settle in turn, each keeping what it ingested."""
    higher, lower = _pair_ordered_against_their_hashes()
    barrier = _FirstWriteBarrier(CONCURRENT_INGEST_COUNT)
    render = ingest_module_under_test.render_sample_pcm

    def render_then_wait(sample_hash: str, trackmod_sample: TrackModSample) -> SamplePCM:
        barrier.reached()
        return render(sample_hash, trackmod_sample)

    monkeypatch.setattr(ingest_module_under_test, "render_sample_pcm", render_then_wait)

    refusals: list[OperationalError] = []

    def ingest(module_hash: str, samples: tuple[TrackModSample, ...]) -> None:
        worker_connection = connect(_database_url)
        try:
            _ingest_pair(worker_connection, tmp_path, song_builder, module_hash=module_hash, samples=samples)
            worker_connection.commit()
        except OperationalError as error:
            refusals.append(error)
        finally:
            worker_connection.close()

    runs = [
        threading.Thread(target=ingest, args=("a" * 64, (higher, lower))),
        threading.Thread(target=ingest, args=("b" * 64, (lower, higher))),
    ]
    for run in runs:
        run.start()
    for run in runs:
        run.join()

    assert refusals == []
    assert len(PostgresModuleRepository(connection).list_all()) == CONCURRENT_INGEST_COUNT
    assert len(PostgresSampleRepository(connection).list_all()) == 2
