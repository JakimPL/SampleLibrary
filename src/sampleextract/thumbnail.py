from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection
from tqdm import tqdm

from samplecore.models.thumbnail import SampleThumbnail
from samplecore.storage import audio_store
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from samplecore.storage.repositories.thumbnail import DuckDBSampleThumbnailRepository, SampleThumbnailRepository
from samplecore.waveform import DEFAULT_THUMBNAIL_BUCKET_COUNT, compute_waveform_peaks


@dataclass(frozen=True)
class ThumbnailBackfillSummary:
    """What one thumbnail backfill pass did, across every sample it considered."""

    catalogued: int
    already_thumbnailed: int
    computed: int


def compute_missing_thumbnails(connection: Connection, library_root: Path, *, force: bool) -> ThumbnailBackfillSummary:
    """Compute and cache a waveform-preview thumbnail for every sample that does not have one yet.

    Idempotent by default: rerunning after a previous pass only computes thumbnails for samples
    added to the catalog since, matching ``run_extraction``'s and ``extract_features``'s own
    "skip what's already done" idempotence. ``force`` recomputes and overwrites every sample's
    thumbnail regardless -- the refresh path for when the configured thumbnail resolution changes.
    """
    sample_repository = DuckDBSampleRepository(connection)
    thumbnail_repository: SampleThumbnailRepository = DuckDBSampleThumbnailRepository(connection)
    samples = sample_repository.list_all()

    already_thumbnailed = 0
    computed = 0
    with start_batch(connection):
        for sample in tqdm(samples, desc="Computing thumbnails"):
            if not force and thumbnail_repository.get(sample.hash) is not None:
                already_thumbnailed += 1
                continue

            pcm = audio_store.read(library_root, sample).pcm
            peaks = compute_waveform_peaks(pcm, bucket_count=DEFAULT_THUMBNAIL_BUCKET_COUNT)
            thumbnail_repository.upsert(
                SampleThumbnail(
                    sample_hash=sample.hash,
                    bucket_count=len(peaks),
                    minimums=tuple(peak.minimum for peak in peaks),
                    maximums=tuple(peak.maximum for peak in peaks),
                )
            )
            computed += 1

    return ThumbnailBackfillSummary(catalogued=len(samples), already_thumbnailed=already_thumbnailed, computed=computed)
