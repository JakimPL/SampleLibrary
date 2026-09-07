from __future__ import annotations

from pydantic import BaseModel
from trackmod.core.notes.pitch import Note
from trackmod.core.samples.depth import BitDepth
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.category import SampleCategory
from samplecore.models.channels import ChannelLayout
from samplecore.models.scalars import Count, Frames, SampleHash
from samplecore.waveform import WaveformPeak


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


class SampleSummary(Sample):
    """One row of a paginated, occurrence-ranked samples listing.

    Ranks samples by identity -- one row per exact content hash -- rather than by equivalence
    class; grouping near-duplicate variants into one row is a distinct future ranking mode, not a
    hidden variant of this one. `display_name` resolves the sample's, possibly conflicting,
    occurrence names via `samplecore.naming.choose_dominant_name`. ``size_bytes`` re-exposes
    ``Sample.stored_bytes`` under its own name: a Pydantic field cannot share a name with an
    inherited plain property without the property silently winning on attribute access.
    ``thumbnail`` is ``None`` for a sample whose cached waveform preview has not been computed yet.
    ``dominant_rate_hz`` resolves the sample's, possibly conflicting, occurrence rates via
    `samplecore.naming.choose_dominant_rate`, and is ``None`` under that same no-occurrences case.
    ``equivalence_class_hash`` identifies the group of near-duplicate variants this sample belongs
    to, resolved from the whole catalog's relation graph, and is ``None`` for a sample with no
    detected relation. ``equivalence_member_count`` is that class's total size (1 for a sample
    with no class), independent of how many of its members are present on this page. ``category``
    resolves the same way ``display_name`` does, via `samplecore.categorization.classify_sample_category`,
    against the sample's own occurrence names together with the names of the instruments reaching it.
    ``dominant_note`` is the note the library plays this sample at most often, which with
    ``dominant_rate_hz`` gives the pitch a preview should sound at; it is ``None`` for a sample whose
    modules have not had their patterns read, and for one no pattern plays. ``hand_label`` is the
    category a person chose for this sample; where it is filled in it is what the sample is, and
    ``category`` beside it stays the keyword table's own guess.
    """

    occurrence_count: Count
    display_name: str
    category: SampleCategory
    hand_label: str | None
    size_bytes: Count
    thumbnail: tuple[WaveformPeak, ...] | None
    dominant_rate_hz: Rate | None
    dominant_note: Note | None
    equivalence_class_hash: str | None
    equivalence_member_count: Count
