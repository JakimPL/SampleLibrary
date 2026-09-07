from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Connection, delete
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.label import LabelSource, SampleLabel
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_properties import MODSampleProperties, SampleOccurrence
from samplecore.models.tracker import TrackerFormat
from samplecore.storage.database import sample, sample_properties
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository

_LABELLED_SAMPLE_HASH: Final[str] = "a" * 64
_REHASHED_SAMPLE_HASH: Final[str] = "b" * 64
_LABELLED_MODULE_HASH: Final[str] = "c" * 64
_OCCURRENCE: Final[SampleOccurrence] = SampleOccurrence(
    module_hash=_LABELLED_MODULE_HASH, instrument_index=0, sample_slot=0
)


def _occupy_slot(connection: Connection, sample_hash: str) -> None:
    """Put a sample in the one module slot these tests label, replacing whatever held it."""
    PostgresSampleRepository(connection).upsert(
        Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=8)
    )
    PostgresSamplePropertiesRepository(connection).upsert(
        MODSampleProperties(sample_hash=sample_hash, occurrence=_OCCURRENCE, name="smp01", rate=8363, volume=64)
    )
    connection.commit()


@pytest.fixture
def catalogued_module(connection: Connection) -> Module:
    repository = PostgresModuleRepository(connection)
    module = Module(
        hash=_LABELLED_MODULE_HASH,
        id=repository.next_id(),
        filename="song.mod",
        tracker=TrackerFormat.MOD,
        title="a song",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    repository.insert(module)
    connection.commit()
    return module


@pytest.fixture
def catalogued_sample(connection: Connection, catalogued_module: Module) -> str:
    _occupy_slot(connection, _LABELLED_SAMPLE_HASH)
    return _LABELLED_SAMPLE_HASH


@pytest.fixture
def stored_label(connection: Connection, catalogued_sample: str) -> SampleLabel:
    label = SampleLabel(
        sample_hash=catalogued_sample,
        label="warm pad",
        occurrence=_OCCURRENCE,
        module_filename="song.mod",
        sample_name="smp01",
        source=LabelSource.SAMPLE,
        labeled_at=datetime.now(UTC),
    )
    PostgresSampleLabelRepository(connection).upsert_many((label,))
    connection.commit()
    return label


@pytest.fixture
def rehash_the_labelled_sample(connection: Connection) -> Callable[[], str]:
    """Stands in for a change in how samples are hashed: the same slot, a differently-named sample.

    Returns the hash the slot holds afterwards, which is what a relink pass is expected to find.
    """

    def rehash() -> str:
        connection.execute(delete(sample_properties))
        connection.execute(delete(sample).where(sample.c.hash == _LABELLED_SAMPLE_HASH))
        connection.commit()
        _occupy_slot(connection, _REHASHED_SAMPLE_HASH)
        return _REHASHED_SAMPLE_HASH

    return rehash


@pytest.fixture
def forget_the_labelled_occurrence(connection: Connection) -> Callable[[], None]:
    """Takes the labelled slot out of the catalog entirely, leaving the label nothing to reach."""

    def forget() -> None:
        connection.execute(delete(sample_properties))
        connection.execute(delete(sample).where(sample.c.hash == _LABELLED_SAMPLE_HASH))
        connection.commit()

    return forget
