from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.instruments.transfer import held
from trackmod.core.instruments.unit import InstrumentUnit
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.songs.song import Song

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.models.thumbnail import SampleThumbnail
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository, SampleRepository
from samplecore.storage.repositories.sample_properties import (
    PostgresSamplePropertiesRepository,
    SamplePropertiesRepository,
)
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, SampleThumbnailRepository
from samplecore.waveform import DEFAULT_THUMBNAIL_BUCKET_COUNT, compute_waveform_peaks
from sampleextract.notes.persistence import persist_module_notes
from sampleextract.rendering import render_properties, render_sample_pcm
from sampleextract.voices import addressable_voices


@dataclass(frozen=True)
class _IngestContext:
    """What every sample occurrence in one module's ingest shares, bundled so it travels as one value."""

    sample_repository: SampleRepository
    properties_repository: SamplePropertiesRepository
    thumbnail_repository: SampleThumbnailRepository
    library_root: Path
    tracker: TrackerFormat
    module_hash: str
    minimum_sample_frames: int


# Every keyword argument below is an independent fact about the module being ingested, with no
# natural subgrouping short of a wrapper this function would be the only caller of.
# pylint: disable-next=too-many-arguments
def ingest_module(
    connection: Connection,
    library_root: Path,
    *,
    module_hash: str,
    tracker: TrackerFormat,
    filename: str,
    file_size: int,
    song: Song,
    ingested_at: datetime,
    minimum_sample_frames: int,
) -> Module:
    """Persist one module and every sample it reaches, as a single all-or-nothing transaction.

    The caller is responsible for confirming this module is not already known before calling --
    this always inserts, and a second call for the same hash raises on the table's own UNIQUE
    constraint rather than silently doing nothing. Idempotent re-runs are ``run_extraction``'s
    concern, not this function's. A sample occurrence shorter than ``minimum_sample_frames`` is
    never catalogued at all -- too short to hold the kind of recorded audio this library's
    equivalence detection and browsing are built around, the same reasoning that already excludes
    an empty placeholder slot.
    """
    module_repository = PostgresModuleRepository(connection)
    context = _IngestContext(
        sample_repository=PostgresSampleRepository(connection),
        properties_repository=PostgresSamplePropertiesRepository(connection),
        thumbnail_repository=PostgresSampleThumbnailRepository(connection),
        library_root=library_root,
        tracker=tracker,
        module_hash=module_hash,
        minimum_sample_frames=minimum_sample_frames,
    )

    voices = addressable_voices(song)

    with start_batch(connection):
        module = Module(
            hash=module_hash,
            id=module_repository.next_id(),
            filename=filename,
            tracker=tracker,
            title=song.name,
            channel_count=song.channels,
            pattern_count=len(song.patterns),
            instrument_count=len(voices.instruments),
            sample_count=len(voices.samples),
            file_size=file_size,
            ingested_at=ingested_at,
        )
        module_repository.insert(module)
        for instrument_index, unit in enumerate(held(voices)):
            _ingest_instrument_unit(context, instrument_index=instrument_index, unit=unit)

        persist_module_notes(
            connection,
            song=song,
            module_id=module.id,
            extracted_at=ingested_at,
        )

    return module


def _ingest_instrument_unit(context: _IngestContext, *, instrument_index: int, unit: InstrumentUnit) -> None:
    for sample_slot, trackmod_sample in enumerate(unit.samples):
        if trackmod_sample.frames < context.minimum_sample_frames:
            continue  # a placeholder slot or a too-short sample has nothing worth cataloguing

        _ingest_sample_occurrence(
            context, instrument_index=instrument_index, sample_slot=sample_slot, trackmod_sample=trackmod_sample
        )


def _ingest_sample_occurrence(
    context: _IngestContext, *, instrument_index: int, sample_slot: int, trackmod_sample: TrackModSample
) -> None:
    sample_hash = compute_sample_hash(
        depth=trackmod_sample.depth,
        channels=ChannelLayout(trackmod_sample.channels),
        frames=trackmod_sample.frames,
        pcm=trackmod_sample.pcm,
    )
    sample_pcm = render_sample_pcm(sample_hash, trackmod_sample)
    context.sample_repository.upsert(sample_pcm.sample)
    audio_store.write(context.library_root, sample_pcm)
    _upsert_thumbnail(context.thumbnail_repository, sample_hash, sample_pcm.pcm)

    occurrence = SampleOccurrence(
        module_hash=context.module_hash, instrument_index=instrument_index, sample_slot=sample_slot
    )
    context.properties_repository.upsert(
        render_properties(
            tracker=context.tracker, sample_hash=sample_hash, occurrence=occurrence, trackmod_sample=trackmod_sample
        )
    )


def _upsert_thumbnail(repository: SampleThumbnailRepository, sample_hash: str, pcm: NDArray[np.float64]) -> None:
    peaks = compute_waveform_peaks(pcm, bucket_count=DEFAULT_THUMBNAIL_BUCKET_COUNT)
    repository.upsert(
        SampleThumbnail(
            sample_hash=sample_hash,
            bucket_count=len(peaks),
            minimums=tuple(peak.minimum for peak in peaks),
            maximums=tuple(peak.maximum for peak in peaks),
        )
    )
