from __future__ import annotations

from pydantic import BaseModel
from trackmod.core.samples.depth import BitDepth

from samplecore.models.base import FROZEN
from samplecore.models.channels import ChannelLayout
from samplecore.models.scalars import Frames, SampleHash


class Sample(BaseModel):
    """The content-addressed identity of one waveform, independent of any module that plays it.

    Two occurrences of the same recorded audio, at the same bit depth and channel layout, collapse
    onto one Sample row. Playback rate is deliberately excluded: it belongs to how a particular
    tracker module occurrence plays this content, not to the content itself, so it lives on
    SampleProperties instead.
    """

    model_config = FROZEN

    hash: SampleHash
    depth: BitDepth
    channels: ChannelLayout
    frames: Frames

    @property
    def stored_bytes(self) -> int:
        """How many bytes this sample's canonical PCM payload occupies, at its own depth."""
        return self.frames * self.channels * self.depth.bytes_per_frame
