from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.progress import tracked
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, SampleThumbnailRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.waveform import compute_thumbnail


@dataclass(frozen=True)
class ThumbnailBackfillSummary:
    """What one thumbnail backfill pass did, across every sample it considered.

    ``unavailable`` counts the samples whose audio lives only in sample files none of which holds it
    now, which a later pass thumbnails once a file is back.
    """

    cataloged: int
    already_thumbnailed: int
    computed: int
    unavailable: int


def compute_missing_thumbnails(connection: Connection, audio: SampleAudio, *, force: bool) -> ThumbnailBackfillSummary:
    """Compute and cache a waveform-preview thumbnail for every sample that does not have one yet.

    Idempotent by default: rerunning after a previous pass only computes thumbnails for samples
    added to the catalog since, matching ``run_extraction``'s and ``extract_features``'s own
    "skip what's already done" idempotence. ``force`` recomputes and overwrites every sample's
    thumbnail regardless -- the refresh path for when the configured thumbnail resolution changes.
    """
    sample_repository = PostgresSampleRepository(connection)
    thumbnail_repository: SampleThumbnailRepository = PostgresSampleThumbnailRepository(connection)
    samples = sample_repository.list_all()

    already_thumbnailed = 0
    computed = 0
    unavailable = 0
    with start_batch(connection):
        for sample in tracked(samples, total=len(samples), label="Computing thumbnails"):
            if not force and thumbnail_repository.get(sample.hash) is not None:
                already_thumbnailed += 1
                continue

            try:
                sample_pcm = audio.read(sample)
            except SampleUnavailableError:
                unavailable += 1
                continue
            thumbnail_repository.upsert(compute_thumbnail(sample.hash, sample_pcm.pcm))
            computed += 1

    return ThumbnailBackfillSummary(
        cataloged=len(samples), already_thumbnailed=already_thumbnailed, computed=computed, unavailable=unavailable
    )
