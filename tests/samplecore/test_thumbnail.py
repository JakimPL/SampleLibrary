from __future__ import annotations

import pytest
from pydantic import ValidationError

from samplecore.models.thumbnail import SampleThumbnail


def _thumbnail(sample_hash: str, *, bucket_count: int = 4, peak_count: int | None = None) -> SampleThumbnail:
    count = bucket_count if peak_count is None else peak_count
    return SampleThumbnail(
        sample_hash=sample_hash,
        bucket_count=bucket_count,
        minimums=tuple(-1.0 for _ in range(count)),
        maximums=tuple(1.0 for _ in range(count)),
    )


def test_a_thumbnail_whose_peaks_match_its_bucket_count_is_accepted(sample_hash_a: str) -> None:
    thumbnail = _thumbnail(sample_hash_a, bucket_count=4)

    assert thumbnail.bucket_count == 4


def test_a_thumbnail_whose_peaks_do_not_match_its_bucket_count_is_rejected(sample_hash_a: str) -> None:
    with pytest.raises(ValidationError, match="declares 4 buckets"):
        _thumbnail(sample_hash_a, bucket_count=4, peak_count=3)


@pytest.mark.parametrize("bucket_count", [0, -1])
def test_a_non_positive_bucket_count_is_rejected(sample_hash_a: str, bucket_count: int) -> None:
    with pytest.raises(ValidationError):
        _thumbnail(sample_hash_a, bucket_count=bucket_count, peak_count=0)
