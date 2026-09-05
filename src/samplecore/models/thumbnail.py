from __future__ import annotations

from pydantic import BaseModel, model_validator

from samplecore.models.base import FROZEN
from samplecore.models.scalars import SampleHash


class SampleThumbnail(BaseModel):
    """A cached, low-resolution amplitude-envelope preview of one Sample's waveform.

    Computed once (at ingest time for a new sample, or by a standalone backfill pass for one
    already catalogued) and reused by every list view that shows this sample, rather than
    recomputed per request. ``bucket_count`` travels with the row so a later change to the
    configured thumbnail resolution is a detectable, explicit fact about a row, not a silent
    mismatch between what is stored and what is currently configured.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    bucket_count: int
    minimums: tuple[float, ...]
    maximums: tuple[float, ...]

    @model_validator(mode="after")
    def _peaks_match_bucket_count(self) -> SampleThumbnail:
        if len(self.minimums) != self.bucket_count or len(self.maximums) != self.bucket_count:
            raise ValueError(
                f"thumbnail declares {self.bucket_count} buckets but carries "
                f"{len(self.minimums)} minimums and {len(self.maximums)} maximums"
            )

        return self
