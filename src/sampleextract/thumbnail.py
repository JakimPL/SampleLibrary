from __future__ import annotations

from dataclasses import dataclass
from itertools import batched
from typing import Final

from sqlalchemy import Connection

from samplecore.progress import ProgressBar
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, SampleThumbnailRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.waveform import compute_thumbnail

THUMBNAIL_COMMIT_ROWS: Final[int] = 1000
THUMBNAILS_LABEL: Final[str] = "Computing thumbnails"


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
    Thumbnails are committed `THUMBNAIL_COMMIT_ROWS` at a time, so a pass stopped partway keeps the
    ones it computed, and progress counts the samples already thumbnailed as done before it began.
    """
    samples = PostgresSampleRepository(connection).list_all()
    thumbnail_repository: SampleThumbnailRepository = PostgresSampleThumbnailRepository(connection)
    thumbnailed = frozenset[str]() if force else thumbnail_repository.sample_hashes()
    pending = [sample for sample in samples if sample.hash not in thumbnailed]
    computed = 0
    unavailable = 0
    with ProgressBar(total=len(samples), label=THUMBNAILS_LABEL, resumed=len(samples) - len(pending)) as progress:
        for batch in batched(pending, THUMBNAIL_COMMIT_ROWS):
            with start_batch(connection):
                for sample in batch:
                    progress.update(1)
                    try:
                        sample_pcm = audio.read(sample)
                    except SampleUnavailableError:
                        unavailable += 1
                        continue
                    thumbnail_repository.upsert(compute_thumbnail(sample.hash, sample_pcm.pcm))
                    computed += 1

    return ThumbnailBackfillSummary(
        cataloged=len(samples),
        already_thumbnailed=len(samples) - len(pending),
        computed=computed,
        unavailable=unavailable,
    )
