from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.instruments.transfer import held
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.songs.song import Song
from trackmod.core.voices.voices import InstrumentVoices

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


@dataclass(frozen=True)
class _Occurrence:
    """One sample slot a keymap reaches, paired with the content hash its waveform carries."""

    instrument_index: int
    sample_slot: int
    sample_hash: str
    trackmod_sample: TrackModSample


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
    concern, not this function's.

    Content comes first and occurrences follow, which is the order that lets several runs ingest at
    once: see ``_store_content`` for the ordering rule the shared rows depend on.
    """
    module_repository = PostgresModuleRepository(connection)
    context = _IngestContext(
        sample_repository=PostgresSampleRepository(connection),
        properties_repository=PostgresSamplePropertiesRepository(connection),
        thumbnail_repository=PostgresSampleThumbnailRepository(connection),
        library_root=library_root,
        tracker=tracker,
        module_hash=module_hash,
    )

    voices = addressable_voices(song)
    occurrences = _reachable_occurrences(voices, minimum_sample_frames=minimum_sample_frames)

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
        _store_content(context, occurrences)
        _store_occurrences(context, occurrences)

        persist_module_notes(
            connection,
            song=song,
            module_id=module.id,
            extracted_at=ingested_at,
        )

    return module


def _reachable_occurrences(voices: InstrumentVoices, *, minimum_sample_frames: int) -> tuple[_Occurrence, ...]:
    """Every sample slot this module's keymaps reach, in the order the catalog numbers them.

    A slot is cataloged once its waveform holds at least ``minimum_sample_frames`` frames -- long
    enough to hold the kind of recorded audio this library's equivalence detection and browsing are
    built around, the same bar an empty placeholder slot is measured against.
    """
    return tuple(
        _occurrence(instrument_index=instrument_index, sample_slot=sample_slot, trackmod_sample=trackmod_sample)
        for instrument_index, unit in enumerate(held(voices))
        for sample_slot, trackmod_sample in enumerate(unit.samples)
        if trackmod_sample.frames >= minimum_sample_frames
    )


def _occurrence(*, instrument_index: int, sample_slot: int, trackmod_sample: TrackModSample) -> _Occurrence:
    sample_hash = compute_sample_hash(
        depth=trackmod_sample.depth,
        channels=ChannelLayout(trackmod_sample.channels),
        frames=trackmod_sample.frames,
        pcm=trackmod_sample.pcm,
    )
    return _Occurrence(
        instrument_index=instrument_index,
        sample_slot=sample_slot,
        sample_hash=sample_hash,
        trackmod_sample=trackmod_sample,
    )


def _store_content(context: _IngestContext, occurrences: tuple[_Occurrence, ...]) -> None:
    """Write each distinct sample this module reaches, taking the shared rows in hash order.

    ``sample`` and ``sample_thumbnail`` are keyed by content hash, which is the one thing two
    modules ingesting at the same moment hold in common -- routine here, since a sample recurs
    across many modules. Ascending hash order is a total order every run agrees on, so concurrent
    transactions reach these rows in the same sequence and each waits only on the one ahead of it,
    which is what lets them proceed without a retry to fall back on.

    Rendering is keyed by hash as well, so a sample filling several of a module's slots is rendered
    once and written once.
    """
    samples_by_hash = _distinct_samples(occurrences)
    for sample_hash in sorted(samples_by_hash):
        sample_pcm = render_sample_pcm(sample_hash, samples_by_hash[sample_hash])
        context.sample_repository.upsert(sample_pcm.sample)
        audio_store.write(context.library_root, sample_pcm)
        _upsert_thumbnail(context.thumbnail_repository, sample_hash, sample_pcm.pcm)


def _distinct_samples(occurrences: tuple[_Occurrence, ...]) -> dict[str, TrackModSample]:
    """One TrackMod sample per content hash, since a hash names one waveform whichever slot holds it."""
    return {occurrence.sample_hash: occurrence.trackmod_sample for occurrence in occurrences}


def _store_occurrences(context: _IngestContext, occurrences: tuple[_Occurrence, ...]) -> None:
    """Write every slot's tracker-specific properties, addressed by the module and slot holding it."""
    for occurrence in occurrences:
        context.properties_repository.upsert(
            render_properties(
                tracker=context.tracker,
                sample_hash=occurrence.sample_hash,
                occurrence=SampleOccurrence(
                    module_hash=context.module_hash,
                    instrument_index=occurrence.instrument_index,
                    sample_slot=occurrence.sample_slot,
                ),
                trackmod_sample=occurrence.trackmod_sample,
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
