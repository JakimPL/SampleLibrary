from __future__ import annotations

from trackmod.core.songs.song import Song
from trackmod.core.voices.convert import raised
from trackmod.core.voices.voices import InstrumentVoices


def addressable_voices(song: Song) -> InstrumentVoices:
    """One song's voice table in the instrument-addressed form the catalog numbers occurrences by.

    Impulse Tracker can store either voice table -- its header states the choice -- and FastTracker 2
    always writes instruments, while Amiga ProTracker and Scream Tracker 3 name a sample straight
    from the cell. Raising a sample table to instruments, one synthetic instrument per sample routing
    every key onto it at that key's own pitch, is what gives every occurrence and every note event
    the same ``(instrument_index, sample_slot)`` addressing whichever table the source module used.
    """
    return song.voices if isinstance(song.voices, InstrumentVoices) else raised(song.voices)
