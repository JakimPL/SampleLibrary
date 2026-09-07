from __future__ import annotations

from pydantic import BaseModel
from trackmod.core.instruments.behaviour import DuplicateAction, DuplicateCheck, NewNoteAction
from trackmod.schema.scalars import Fadeout, InstrumentVolume, Panning

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index


class ModuleInstrument(BaseModel):
    """One instrument slot of a module, numbered as its voice table numbers it.

    Sample-addressed formats reach a waveform straight from the cell, and extraction raises those
    tables into instruments routing every key onto one sample, so a row exists here for those too.
    That is what keeps ``instrument_index`` meaning the same thing in every format and addressing
    the same occurrences as ``sample_properties``.

    The name is what this carries that a sample does not: an instrument is named separately from the
    waveforms its keys reach, so it records what the author called the voice itself.
    """

    model_config = FROZEN

    module_id: Index
    instrument_index: Index
    name: str
    fadeout: Fadeout
    global_volume: InstrumentVolume
    panning: Panning | None
    new_note_action: NewNoteAction
    duplicate_check: DuplicateCheck
    duplicate_action: DuplicateAction
