from __future__ import annotations

from typing import Final

import numpy as np

from samplemorph.partials.settings import PartialSettings
from tests.samplemorph.partials.conftest import (
    HOP_LENGTH,
    RATE_HZ,
    times,
    tracks_of,
    vibrato_frequency,
    vibrato_tone,
)

FUNDAMENTAL_HZ: Final[float] = 220.0
HARMONIC_COUNT: Final[int] = 8
VIBRATO_DEPTH_CENTS: Final[float] = 50.0
VIBRATO_RATE_HZ: Final[float] = 5.5
VIBRATO_CENTS_TOLERANCE: Final[float] = 5.0
EDGE_FRAMES: Final[int] = 40
NOISE_ENERGY_SHARE_CEILING: Final[float] = 0.02
BLIP_SECONDS: Final[float] = 0.02
SHORTEST_TRACK_SECONDS: Final[float] = 0.15


def test_every_harmonic_of_a_vibrato_tone_is_one_track_following_its_pitch() -> None:
    """The window averages the swing over its own length, which shallows a 5.5 Hz vibrato by about an eighth."""
    tracks = tracks_of(
        vibrato_tone(
            fundamental_hz=FUNDAMENTAL_HZ,
            depth_cents=VIBRATO_DEPTH_CENTS,
            rate_hz=VIBRATO_RATE_HZ,
            harmonic_count=HARMONIC_COUNT,
        )
    )

    frame_times = np.arange(tracks.frame_count) * HOP_LENGTH / RATE_HZ
    truth = vibrato_frequency(
        frame_times, fundamental_hz=FUNDAMENTAL_HZ, depth_cents=VIBRATO_DEPTH_CENTS, rate_hz=VIBRATO_RATE_HZ
    )
    inner = slice(EDGE_FRAMES, tracks.frame_count - EDGE_FRAMES)
    assert tracks.track_count == HARMONIC_COUNT
    for index in range(tracks.track_count):
        harmonic = round(float(np.median(tracks.frequency_hz[index])) / FUNDAMENTAL_HZ)
        error = 1200.0 * np.log2(tracks.frequency_hz[index, inner] / (harmonic * truth[inner]))
        assert tracks.sounding[index, inner].all()
        assert float(np.sqrt(np.mean(error**2))) <= VIBRATO_CENTS_TOLERANCE


def test_noise_leaves_almost_none_of_its_energy_in_tracks() -> None:
    noise = np.random.default_rng(5).normal(size=times().shape[0])

    tracks = tracks_of(noise)

    track_energy = float((tracks.amplitude.astype(np.float64) ** 2 / 2.0).sum())
    noise_energy = float(np.mean(noise**2)) * tracks.frame_count
    assert track_energy / noise_energy <= NOISE_ENERGY_SHARE_CEILING


def test_a_partial_briefer_than_the_shortest_track_is_left_out() -> None:
    """The analysis window smears a brief partial over its own length, so the shortest track here outlasts both."""
    seconds = times()
    steady = np.sin(2.0 * np.pi * 440.0 * seconds)
    blip = np.where((seconds > 0.5) & (seconds < 0.5 + BLIP_SECONDS), np.sin(2.0 * np.pi * 1500.0 * seconds), 0.0)

    tracks = tracks_of(steady + blip, settings=PartialSettings(minimum_track_seconds=SHORTEST_TRACK_SECONDS))

    assert tracks.track_count == 1
    assert abs(float(np.median(tracks.frequency_hz[0])) - 440.0) < 1.0
