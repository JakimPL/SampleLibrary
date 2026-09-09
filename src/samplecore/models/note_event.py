from __future__ import annotations

from pydantic import BaseModel, model_validator
from trackmod.core.notes.pitch import Note
from trackmod.schema.scalars import Rate

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Count, Index, SampleHash


class SampleNoteUsage(BaseModel):
    """How often one sample is heard at one note struck against one occurrence rate.

    A sample-hash carries no pitch of its own: what a waveform sounds at is decided per note event,
    against the rate of the occurrence that event reaches. Both halves travel together because both
    are needed -- the rate carries the tuning and transpose a tracker folded into it, the note says
    how far the key moves it -- and only the pair says how fast the frames are really read.
    """

    model_config = FROZEN

    reference_rate_hz: Rate
    sounded_note: Note
    event_count: Count


class SamplePlaybackRate(BaseModel):
    """How often one sample is heard at one effective playback rate, across every module playing it.

    This is the rate a waveform's frames are really read at: one number standing for an occurrence
    rate and a pressed key together. Read as a group, these say which speeds a sample is used at and
    how much each is leaned on, which is what lets a preview sound it the way the library does.
    """

    model_config = FROZEN

    rate_hz: Rate
    event_count: Count


class SampleNoteStatistics(BaseModel):
    """How one sample is played across the catalog: at how many pitches, over what span, how often.

    A waveform carries no pitch of its own, so what a sample is used for shows in the notes the
    library plays it at. A sample struck at one pitch throughout is used as a fixed sound, and one
    spread over a wide span is played as an instrument. `strike_count` says how much evidence either
    reading rests on, since a sample struck twice can show at most two pitches whatever it is.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    distinct_pitch_count: Count
    lowest_note: Note
    highest_note: Note
    strike_count: Count

    @property
    def pitch_span_semitones(self) -> int:
        """How far apart the lowest and highest notes this sample is played at sit."""
        return self.highest_note.midi - self.lowest_note.midi


class NoteEvent(BaseModel):
    """One key pressed at one grid position of a module's patterns, carrying what that key sounds.

    A tracker cell names a key and, usually, an instrument. What the pair plays is decided by the
    instrument's keymap, which routes a key onto a sample together with the note that sample sounds
    at -- so the key a composer wrote and the pitch a listener hears are two different values. This
    model carries the outcome of that routing, which is what lets every reader reach the pitch a
    sample is heard at while the keymap itself stays inside extraction.

    ``sounded_note`` and ``sample_slot`` are filled in as far as the module allows. A cell naming no
    instrument leaves both open, since the routing follows whichever instrument the channel already
    carries. A key routed onto a sample the catalog holds no occurrence for keeps its
    ``sounded_note`` and leaves ``sample_slot`` open.

    The sounding rate follows from ``sounded_note`` and the occurrence's own rate, so it is computed
    where it is needed rather than stored here.
    """

    model_config = FROZEN

    module_id: Index
    pattern_index: Index
    row_index: Index
    channel_index: Index
    note: Note
    sounded_note: Note | None
    instrument_index: Index | None
    sample_slot: Index | None

    @model_validator(mode="after")
    def _resolution_follows_an_instrument(self) -> NoteEvent:
        if self.instrument_index is None and (self.sounded_note is not None or self.sample_slot is not None):
            raise ValueError("a resolved note or sample slot requires the instrument index it was routed through")

        return self
