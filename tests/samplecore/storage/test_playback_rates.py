from __future__ import annotations

from sqlalchemy import Connection
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.storage.playback_rates import resolved_playback_rates
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

OCCURRENCE_RATE_HZ = 8363
NOTE_EVENT_RATE_HZ = 16726


def _add_occurrence(connection: Connection, *, sample: Sample, module: Module, slot: int, rate: int) -> None:
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=slot),
            name="tone",
            rate=rate,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )


def test_the_note_events_rate_speaks_first(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, rate=OCCURRENCE_RATE_HZ)
    PostgresSamplePlaybackRateRepository(connection).replace_all({stored_sample.hash: NOTE_EVENT_RATE_HZ})

    assert resolved_playback_rates(connection, [stored_sample.hash]) == {stored_sample.hash: NOTE_EVENT_RATE_HZ}


def test_the_occurrences_answer_for_a_sample_the_note_events_never_reached(
    connection: Connection, stored_sample: Sample, stored_module: Module
) -> None:
    _add_occurrence(connection, sample=stored_sample, module=stored_module, slot=0, rate=OCCURRENCE_RATE_HZ)

    assert resolved_playback_rates(connection, [stored_sample.hash]) == {stored_sample.hash: OCCURRENCE_RATE_HZ}


def test_a_sample_the_catalog_never_plays_maps_to_none(connection: Connection, stored_sample: Sample) -> None:
    assert resolved_playback_rates(connection, [stored_sample.hash, "f" * 64]) == {
        stored_sample.hash: None,
        "f" * 64: None,
    }
