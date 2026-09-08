from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from sampleextract.thumbnail import ThumbnailBackfillSummary, compute_missing_thumbnails

FRAMES = 64


def _store_sample(connection: Connection, library_root: Path, sample_hash: str) -> Sample:
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAMES)
    PostgresSampleRepository(connection).upsert(sample)
    connection.commit()
    pcm = np.linspace(-1.0, 1.0, FRAMES).reshape(FRAMES, 1)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def test_computes_a_thumbnail_for_every_sample_with_none_yet(connection: Connection, tmp_path: Path) -> None:
    sample_a = _store_sample(connection, tmp_path, "a" * 64)
    sample_b = _store_sample(connection, tmp_path, "b" * 64)

    summary = compute_missing_thumbnails(connection, tmp_path, force=False)

    assert summary == ThumbnailBackfillSummary(cataloged=2, already_thumbnailed=0, computed=2)
    thumbnail_repository = PostgresSampleThumbnailRepository(connection)
    assert thumbnail_repository.get(sample_a.hash) is not None
    assert thumbnail_repository.get(sample_b.hash) is not None


def test_a_second_pass_skips_every_sample_already_thumbnailed(connection: Connection, tmp_path: Path) -> None:
    _store_sample(connection, tmp_path, "a" * 64)
    compute_missing_thumbnails(connection, tmp_path, force=False)

    summary = compute_missing_thumbnails(connection, tmp_path, force=False)

    assert summary.cataloged == 1
    assert summary.already_thumbnailed == 1
    assert summary.computed == 0


def test_force_recomputes_every_sample_regardless_of_what_is_already_cached(
    connection: Connection, tmp_path: Path
) -> None:
    _store_sample(connection, tmp_path, "a" * 64)
    compute_missing_thumbnails(connection, tmp_path, force=False)

    summary = compute_missing_thumbnails(connection, tmp_path, force=True)

    assert summary.cataloged == 1
    assert summary.already_thumbnailed == 0
    assert summary.computed == 1
