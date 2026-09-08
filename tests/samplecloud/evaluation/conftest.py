from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy import Connection
from trackmod.core.notes.pitch import Note
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment, SampleFeatureVector
from samplecore.models.module import Module
from samplecore.models.note_event import NoteEvent
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

SAMPLES_PER_CATEGORY = 8
FEATURE_DIMENSIONS = 6
SEEDED_CATEGORIES = ("kick", "snare", "bass", "lead")
SAMPLE_RATE_HZ = 8_363


@dataclass(frozen=True)
class SeededCatalog:
    """A small catalog whose categories and note usage a descriptor can be scored against."""

    experiment_id: int
    sample_hashes: tuple[str, ...]
    categories: tuple[str, ...]


def seed_catalog(connection: Connection, *, separable: bool) -> SeededCatalog:
    """Put a few samples per keyword category in the catalog, each played at a known set of pitches.

    `separable` decides whether a sample's feature vector says which category it belongs to. A
    separable body lets a test assert that a working metric finds the structure; a body of noise
    lets a test assert that the same metric reports its absence rather than inventing it.
    """
    experiment_repository = PostgresExperimentRepository(connection)
    experiment_id = experiment_repository.next_id()
    experiment_repository.insert(
        Experiment(id=experiment_id, backend_name="stub", params={}, created_at=datetime.now(UTC), label=None)
    )
    sample_repository = PostgresSampleRepository(connection)
    module_repository = PostgresModuleRepository(connection)
    properties_repository = PostgresSamplePropertiesRepository(connection)
    note_repository = PostgresNoteEventRepository(connection)

    generator = np.random.default_rng(0)
    hashes: list[str] = []
    categories: list[str] = []
    vectors: list[SampleFeatureVector] = []
    index = 0
    for category_index, category in enumerate(SEEDED_CATEGORIES):
        for member in range(SAMPLES_PER_CATEGORY):
            index += 1
            sample_hash = format(index, "064x")
            sample_repository.upsert(
                Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4096)
            )
            module = Module(
                id=module_repository.next_id(),
                hash=format(index + 5000, "064x"),
                filename=f"song{index}.xm",
                tracker=TrackerFormat.XM,
                title="untitled",
                channel_count=4,
                pattern_count=1,
                instrument_count=1,
                sample_count=1,
                file_size=1024,
                ingested_at=datetime.now(UTC),
            )
            module_repository.insert(module)
            properties_repository.upsert(
                XMSampleProperties(
                    sample_hash=sample_hash,
                    occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
                    name=f"{category} {member}",
                    rate=SAMPLE_RATE_HZ,
                    volume=64,
                    tuning=Tuning(relative_note=0, finetune=0),
                )
            )
            note_repository.insert_many(_note_events(module.id, pitch_count=category_index + 1, strike_count=12))
            center = np.zeros(FEATURE_DIMENSIONS)
            if separable:
                center[category_index] = 10.0
            vectors.append(
                SampleFeatureVector(
                    experiment_id=experiment_id,
                    sample_hash=sample_hash,
                    vector=tuple(center + generator.normal(0.0, 0.1, FEATURE_DIMENSIONS)),
                    computed_at=datetime.now(UTC),
                )
            )
            hashes.append(sample_hash)
            categories.append(category)

    PostgresSampleFeatureVectorRepository(connection).insert_many(vectors)
    connection.commit()
    return SeededCatalog(experiment_id=experiment_id, sample_hashes=tuple(hashes), categories=tuple(categories))


def _note_events(module_id: int, *, pitch_count: int, strike_count: int) -> list[NoteEvent]:
    """Strikes spread over `pitch_count` distinct pitches, so a sample's note statistics are known."""
    return [
        NoteEvent(
            module_id=module_id,
            pattern_index=0,
            row_index=strike,
            channel_index=0,
            note=Note(48 + strike % pitch_count),
            sounded_note=Note(48 + strike % pitch_count),
            instrument_index=0,
            sample_slot=0,
        )
        for strike in range(strike_count)
    ]


@pytest.fixture(name="separable_catalog")
def separable_catalog_fixture(connection: Connection) -> SeededCatalog:
    return seed_catalog(connection, separable=True)
