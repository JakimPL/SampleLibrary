from __future__ import annotations

import math

from trackmod.core.notes.pitch import Note
from trackmod.schema.scalars import Rate
from trackmod.spec.pitch import NOTES_PER_OCTAVE, RATE_NOTE


def sounding_rate_hz(*, reference_rate_hz: Rate, sounded_note: Note) -> float:
    """The rate a sample's frames are read at to sound one note.

    An occurrence's stored rate is a reference: the speed the waveform plays at when the key every
    tracker counts its tuning from -- C-5 -- is pressed. Every other note moves that rate by the
    equal-tempered ratio between the two, which is what makes a note, rather than a rate, the thing a
    sample is actually played at.
    """
    # math.pow rather than `**`: typeshed types float exponentiation as returning Any, since a
    # negative base and a fractional exponent give a complex number.
    return reference_rate_hz * math.pow(2.0, (sounded_note.value - RATE_NOTE) / NOTES_PER_OCTAVE)
