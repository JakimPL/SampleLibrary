from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from numpy.typing import NDArray
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import KeyAssignment, pitched_keymap, routed_keymap
from trackmod.core.notes.pitch import Note
from trackmod.core.patterns.builder import PatternBuilder
from trackmod.core.patterns.cell import Cell
from trackmod.core.patterns.grid import Pattern
from trackmod.core.samples.depth import BitDepth
from trackmod.core.samples.sample import Sample
from trackmod.core.songs.order import OrderList
from trackmod.core.songs.playback import Playback
from trackmod.core.songs.song import Song
from trackmod.core.voices.voices import InstrumentVoices, SampleVoices
from trackmod.limits.compliance import Compliance
from trackmod.trackers.it.module import ITModule
from trackmod.trackers.mod.module import MODModule
from trackmod.trackers.s3m.module import S3MModule
from trackmod.trackers.xm.module import XMModule

SAMPLE_RATE = 44100
# Amiga ProTracker's finetune-derived rates and its pattern length are both fixed, structural
# bounds (unlike XM/IT's own, looser ones) -- 8363 Hz is the format's own untransposed C-3 rate,
# and every pattern must hold exactly this many rows.
MOD_SAMPLE_RATE = 8363
SAMPLE_VOICES_PATTERN_ROWS = 64
PLAYED_NOTE = Note(60)
ROUTED_KEY = Note(48)
ROUTED_SOUNDED_NOTE = Note(72)


def _waveform(frames: int, *, seed: int) -> NDArray[np.float64]:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, frames)


def _one_note_pattern(*, rows: int, note: Note) -> Pattern:
    """A grid whose first row presses one key on the first instrument, leaving every other row bare."""
    builder = PatternBuilder(rows=rows, channels=1)
    builder.place(0, 0, Cell(note=note, instrument=0))
    return builder.build()


def _build_song(*, samples: tuple[Sample, ...], instruments: tuple[Instrument, ...]) -> Song:
    """A song wide and long enough to be writable by either format, playing one key on one row.

    The single note keeps every ingest test exercising note extraction alongside the samples and
    instruments the rest of the pipeline reads.
    """
    return Song(
        name="probe",
        channels=1,
        patterns=(_one_note_pattern(rows=1, note=PLAYED_NOTE),),
        order=OrderList(entries=(0,)),
        voices=InstrumentVoices(instruments=instruments, samples=samples),
        playback=Playback(speed=6, tempo=125),
    )


def _one_instrument_song(sample_name: str) -> Song:
    sample = Sample(name=sample_name, pcm=_waveform(32, seed=1), rate=SAMPLE_RATE)
    instrument = Instrument(name="voice", keymap=pitched_keymap(sample=0))
    return _build_song(samples=(sample,), instruments=(instrument,))


def _one_sample_song(sample_name: str, *, rate: int, depth: BitDepth = BitDepth.SIXTEEN) -> Song:
    """A song for a format whose cells name a sample directly, with no instrument indirection."""
    sample = Sample(name=sample_name, pcm=_waveform(32, seed=1), rate=rate, depth=depth)
    return Song(
        name="probe",
        channels=1,
        patterns=(_one_note_pattern(rows=SAMPLE_VOICES_PATTERN_ROWS, note=PLAYED_NOTE),),
        order=OrderList(entries=(0,)),
        voices=SampleVoices(samples=(sample,)),
        playback=Playback(speed=6, tempo=125),
    )


@pytest.fixture
def played_note() -> Note:
    """The key every single-note module fixture presses."""
    return PLAYED_NOTE


@pytest.fixture
def routed_key() -> Note:
    """The key ``transposing_it_module_bytes`` presses."""
    return ROUTED_KEY


@pytest.fixture
def routed_sounded_note() -> Note:
    """The note ``transposing_it_module_bytes`` sounds when ``routed_key`` is pressed."""
    return ROUTED_SOUNDED_NOTE


@pytest.fixture
def song_builder() -> Callable[[tuple[Sample, ...], tuple[Instrument, ...]], Song]:
    """Assembles a song from given samples and instruments -- the shape every ingest test needs."""

    def build(samples: tuple[Sample, ...], instruments: tuple[Instrument, ...]) -> Song:
        return _build_song(samples=samples, instruments=instruments)

    return build


@pytest.fixture
def xm_module_bytes() -> bytes:
    return XMModule.from_song(_one_instrument_song("lead"), compliance=Compliance.EXTENDED).to_bytes()


@pytest.fixture
def it_module_bytes() -> bytes:
    return ITModule.from_song(_one_instrument_song("kick"), compliance=Compliance.EXTENDED).to_bytes()


@pytest.fixture
def mod_module_bytes() -> bytes:
    song = _one_sample_song("chip", rate=MOD_SAMPLE_RATE, depth=BitDepth.EIGHT)
    return MODModule.from_song(song, compliance=Compliance.EXTENDED).to_bytes()


@pytest.fixture
def s3m_module_bytes() -> bytes:
    return S3MModule.from_song(_one_sample_song("pluck", rate=SAMPLE_RATE), compliance=Compliance.EXTENDED).to_bytes()


@pytest.fixture
def transposing_it_module_bytes() -> bytes:
    """An Impulse Tracker module whose keymap sounds its one key at another key's pitch.

    Impulse Tracker is the format that carries a routing like this through a file, which is what
    makes the note a sample is heard at genuinely different from the key a cell states.
    """
    sample = Sample(name="bell", pcm=_waveform(32, seed=2), rate=SAMPLE_RATE)
    instrument = Instrument(
        name="routed voice",
        keymap=routed_keymap({ROUTED_KEY: KeyAssignment(sample=0, note=ROUTED_SOUNDED_NOTE)}),
    )
    song = Song(
        name="probe",
        channels=1,
        patterns=(_one_note_pattern(rows=1, note=ROUTED_KEY),),
        order=OrderList(entries=(0,)),
        voices=InstrumentVoices(instruments=(instrument,), samples=(sample,)),
        playback=Playback(speed=6, tempo=125),
    )
    return ITModule.from_song(song, compliance=Compliance.EXTENDED).to_bytes()
