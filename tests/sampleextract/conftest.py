from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from numpy.typing import NDArray
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import pitched_keymap
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


def _waveform(frames: int, *, seed: int) -> NDArray[np.float64]:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, frames)


def _build_song(*, samples: tuple[Sample, ...], instruments: tuple[Instrument, ...]) -> Song:
    """A song wide and long enough to be writable by either format, with a single silent pattern --
    the pipeline reads instruments and samples only, so what a pattern plays is irrelevant here.
    """
    return Song(
        name="probe",
        channels=1,
        patterns=(Pattern.empty(rows=1, channels=1),),
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
        patterns=(Pattern.empty(rows=SAMPLE_VOICES_PATTERN_ROWS, channels=1),),
        order=OrderList(entries=(0,)),
        voices=SampleVoices(samples=(sample,)),
        playback=Playback(speed=6, tempo=125),
    )


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
