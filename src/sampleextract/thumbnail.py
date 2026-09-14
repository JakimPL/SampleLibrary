from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection
from tqdm import tqdm

from samplecore.storage import audio_store
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, SampleThumbnailRepository
from samplecore.waveform import compute_thumbnail


@dataclass(frozen=True)
class ThumbnailBackfillSummary:
    """What one thumbnail backfill pass did, across every sample it considered."""

    cataloged: int
    already_thumbnailed: int
    computed: int


def compute_missing_thumbnails(connection: Connection, library_root: Path, *, force: bool) -> ThumbnailBackfillSummary:
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
    with start_batch(connection):
        for sample in tqdm(samples, desc="Computing thumbnails"):
            if not force and thumbnail_repository.get(sample.hash) is not None:
                already_thumbnailed += 1
                continue

            thumbnail_repository.upsert(compute_thumbnail(sample.hash, audio_store.read(library_root, sample).pcm))
            computed += 1

    return ThumbnailBackfillSummary(cataloged=len(samples), already_thumbnailed=already_thumbnailed, computed=computed)
