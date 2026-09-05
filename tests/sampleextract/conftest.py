from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import pitched_keymap
from trackmod.core.patterns.grid import Pattern
from trackmod.core.samples.sample import Sample
from trackmod.core.songs.order import OrderList
from trackmod.core.songs.playback import Playback
from trackmod.core.songs.song import Song
from trackmod.limits.compliance import Compliance
from trackmod.trackers.it.module import ITModule
from trackmod.trackers.xm.module import XMModule

from samplecore.storage.database import connect

SAMPLE_RATE = 44100


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
        instruments=instruments,
        samples=samples,
        playback=Playback(speed=6, tempo=125),
    )


def _one_instrument_song(sample_name: str) -> Song:
    sample = Sample(name=sample_name, pcm=_waveform(32, seed=1), rate=SAMPLE_RATE)
    instrument = Instrument(name="voice", keymap=pitched_keymap(sample=0))
    return _build_song(samples=(sample,), instruments=(instrument,))


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
def connection() -> Iterator[Connection]:
    open_connection = connect(Path(":memory:"))
    yield open_connection
    open_connection.close()
