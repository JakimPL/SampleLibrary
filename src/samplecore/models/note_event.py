from __future__ import annotations

from pydantic import BaseModel, model_validator
from trackmod.core.notes.pitch import Note

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Count, Index


class SampleNoteUsage(BaseModel):
    """How often one sample is heard at one note, counted across every module that plays it.

    A sample-hash carries no pitch of its own; what it is heard at is decided per note event. Read
    together, these say which pitches a waveform is actually used at and how much each is leaned on,
    which is what grounds a preview in the way the library really plays it.
    """

    model_config = FROZEN

    sounded_note: Note
    event_count: Count


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
