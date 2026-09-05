from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.module import Module
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.module import DuckDBModuleRepository
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample_properties import DuckDBSamplePropertiesRepository
from samplecore.storage.stats import compute_library_stats


def test_compute_library_stats_against_a_small_seeded_catalog(
    connection: duckdb.DuckDBPyConnection, stored_module: Module, stored_sample: Sample, stored_sample_b: Sample
) -> None:
    xm_module_repository = DuckDBModuleRepository(connection)
    xm_module = Module(
        hash=format(7, "064x"),
        id=xm_module_repository.next_id(),
        filename="song.xm",
        tracker=TrackerFormat.XM,
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    xm_module_repository.insert(xm_module)

    DuckDBSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=stored_sample.hash,
            occurrence=SampleOccurrence(module_hash=xm_module.hash, instrument_index=0, sample_slot=0),
            name="lead",
            rate=8363,
            volume=64,
            loop=Loop(begin=0, end=4, mode=LoopMode.FORWARD),
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )

    relation_repository = DuckDBSampleRelationRepository(connection)
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=stored_sample.hash,
            reference_hash=stored_sample_b.hash,
            relation_type=RelationType.BIT_DEPTH_VARIANT,
            method="bit_depth_variant/mse_v1",
            confidence=0.9,
            evidence={"rms_error": 0.001, "max_abs_error": 0.002},
            detected_at=datetime.now(UTC),
        )
    )

    stats = compute_library_stats(connection)

    assert stats.module_count == 2
    assert stats.sample_count == 2
    assert stats.sample_properties_count == 1
    assert {(item.tracker, item.module_count) for item in stats.modules_by_tracker} == {
        (TrackerFormat.IT, 1),
        (TrackerFormat.XM, 1),
    }
    assert {(item.relation_type, item.relation_count) for item in stats.relations_by_type} == {
        (RelationType.BIT_DEPTH_VARIANT, 1)
    }
    assert stats.total_stored_bytes == stored_sample.stored_bytes + stored_sample_b.stored_bytes


def test_compute_library_stats_on_an_empty_catalog(connection: duckdb.DuckDBPyConnection) -> None:
    stats = compute_library_stats(connection)

    assert stats.module_count == 0
    assert stats.sample_count == 0
    assert stats.sample_properties_count == 0
    assert stats.modules_by_tracker == ()
    assert stats.relations_by_type == ()
    assert stats.total_stored_bytes == 0
