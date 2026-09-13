from __future__ import annotations

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from sampleextract.discovery import discover_modules
from sampleextract.notes.persistence import clear_module_notes
from sampleextract.notes.playback_rates import record_playback_rates
from sampleextract.progress import ProgressSink
from sampleextract.run import run_extraction

OCTAVE_RATIO = 2
NO_MINIMUM_FRAMES = 1


def _stored_rate(connection: Connection, sample_hash: str) -> int:
    """The rate this sample's only occurrence declares, which is what it sounds at the reference key."""
    occurrences = PostgresSamplePropertiesRepository(connection).list_for_sample(sample_hash)
    return occurrences[0].rate


@pytest.fixture
def transposing_corpus(
    connection: Connection,
    config: LibraryConfig,
    transposing_it_module_bytes: bytes,
    progress: ProgressSink,
) -> LibraryConfig:
    """One cataloged module whose keymap sounds its only key an octave above the reference key.

    Ingested with no frame floor, so the short probe waveform is cataloged as an occurrence the
    module's own note events reach.
    """
    corpus = config.model_copy(update={"minimum_sample_frames": NO_MINIMUM_FRAMES})
    (corpus.module_source_directory / "song.it").write_bytes(transposing_it_module_bytes)
    run_extraction(corpus, connection, discover_modules(corpus.module_source_directory), progress=progress)
    connection.commit()
    return corpus


def test_a_recorded_rate_is_the_speed_the_library_really_reads_the_waveform_at(
    connection: Connection, transposing_corpus: LibraryConfig
) -> None:
    """The one key this module presses sounds an octave above the key a stored rate is counted from."""
    recorded = record_playback_rates(connection)

    rate_by_hash = PostgresSamplePlaybackRateRepository(connection).list_all()
    assert recorded == 1
    assert rate_by_hash == {
        sample_hash: _stored_rate(connection, sample_hash) * OCTAVE_RATIO for sample_hash in rate_by_hash
    }


def test_a_catalog_whose_patterns_are_unread_records_nothing(
    connection: Connection, transposing_corpus: LibraryConfig
) -> None:
    for module in PostgresModuleRepository(connection).list_all():
        clear_module_notes(connection, module_id=module.id)

    connection.commit()

    assert record_playback_rates(connection) == 0
    assert PostgresSamplePlaybackRateRepository(connection).list_all() == {}


def test_a_later_pass_answers_for_the_catalog_as_it_stands(
    connection: Connection, transposing_corpus: LibraryConfig
) -> None:
    record_playback_rates(connection)
    for module in PostgresModuleRepository(connection).list_all():
        clear_module_notes(connection, module_id=module.id)

    connection.commit()
    record_playback_rates(connection)

    assert PostgresSamplePlaybackRateRepository(connection).list_all() == {}
