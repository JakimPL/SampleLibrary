from __future__ import annotations

import numpy as np
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecloud.hearing import Hearing, Reading, hearing_for
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository

FRAMES = 64
SAMPLE_HASH = "a" * 64


def _pcm() -> np.ndarray:
    return np.random.default_rng(0).uniform(-1.0, 1.0, (FRAMES, 1))


def test_a_nominal_reading_hands_the_frames_over_as_stored() -> None:
    pcm = _pcm()

    heard = Hearing(reading=Reading.NOMINAL, playback_rate_by_hash={SAMPLE_HASH: NOMINAL_WAV_RATE // 2}).hear(
        SAMPLE_HASH, pcm
    )

    assert heard is pcm


def test_a_sample_played_an_octave_below_its_stored_rate_lasts_twice_as_long() -> None:
    hearing = Hearing(reading=Reading.HEARD_RATE, playback_rate_by_hash={SAMPLE_HASH: NOMINAL_WAV_RATE // 2})

    heard = hearing.hear(SAMPLE_HASH, _pcm())

    assert heard.shape == (2 * FRAMES, 1)


def test_a_sample_the_library_never_plays_keeps_the_nominal_reading() -> None:
    hearing = Hearing(reading=Reading.HEARD_RATE, playback_rate_by_hash={})
    pcm = _pcm()

    assert hearing.hear(SAMPLE_HASH, pcm) is pcm


def test_the_hearing_reads_the_recorded_playback_rates_of_the_catalog(connection: Connection) -> None:
    PostgresSampleRepository(connection).upsert(
        Sample(hash=SAMPLE_HASH, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAMES)
    )
    PostgresSamplePlaybackRateRepository(connection).replace_all({SAMPLE_HASH: 8363})

    hearing = hearing_for(connection, Reading.HEARD_RATE)

    assert hearing.playback_rate_by_hash == {SAMPLE_HASH: 8363}
    assert hearing_for(connection, Reading.NOMINAL).playback_rate_by_hash == {}
