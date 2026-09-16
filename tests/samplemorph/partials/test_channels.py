from __future__ import annotations

from typing import Final

import numpy as np

from samplemorph.partials.channels import FREE_PARTIAL, channelize
from samplemorph.partials.settings import NoteSettings
from samplemorph.partials.tracks import CENTS_PER_OCTAVE
from tests.samplemorph.partials.conftest import harmonics, times, tracks_of

SETTINGS: Final[NoteSettings] = NoteSettings()
HARMONIC_COUNT: Final[int] = 8
CENTS_TOLERANCE: Final[float] = 5.0
AMPLITUDE_TOLERANCE_DB: Final[float] = 1.0
C4, E4, G4 = 261.63, 329.63, 392.0
SHARED_HZ: Final[float] = 784.0
SHARED_REACH_HZ: Final[float] = 8.0


def _middle(values: np.ndarray) -> float:
    inner = values[values.shape[0] // 4 : 3 * values.shape[0] // 4]
    return float(np.median(inner))


def test_every_harmonic_of_a_note_becomes_a_channel_on_that_note_s_own_pitch() -> None:
    channels = channelize(tracks_of(harmonics(220.0, harmonic_count=HARMONIC_COUNT)), settings=SETTINGS)

    assert channels.note_count == 1
    assert channels.channel_count == HARMONIC_COUNT
    for index in range(channels.channel_count):
        harmonic = int(channels.harmonic[index])
        read = _middle(channels.tracks.frequency_hz[index])
        assert abs(CENTS_PER_OCTAVE * np.log2(read / (harmonic * 220.0))) <= CENTS_TOLERANCE


def test_a_partial_two_notes_share_is_split_between_them() -> None:
    """A fifth's second harmonic is the lower note's third, and the two halves sum to the partial as measured."""
    chord = (harmonics(C4, harmonic_count=HARMONIC_COUNT) + harmonics(G4, harmonic_count=HARMONIC_COUNT)) / 2.0
    tracks = tracks_of(chord)

    channels = channelize(tracks, settings=SETTINGS)

    def near(frequency: np.ndarray, amplitude: np.ndarray) -> list[float]:
        return [
            _middle(amplitude[index])
            for index in range(frequency.shape[0])
            if abs(_middle(frequency[index]) - SHARED_HZ) <= SHARED_REACH_HZ
        ]

    halves = near(channels.tracks.frequency_hz, channels.tracks.amplitude)
    measured = near(tracks.frequency_hz, tracks.amplitude)
    assert len(halves) == 2
    assert abs(20.0 * np.log10(sum(halves) / sum(measured))) <= AMPLITUDE_TOLERANCE_DB


def test_a_sound_of_scattered_partials_keeps_every_one_of_them_free() -> None:
    seconds = times()
    ratios = (1.0, 2.756, 5.404, 8.933, 13.34)
    struck = np.sum([np.sin(2.0 * np.pi * 300.0 * ratio * seconds) for ratio in ratios], axis=0)

    channels = channelize(tracks_of(0.5 * struck / np.abs(struck).max()), settings=SETTINGS)

    assert channels.note_count == 0
    assert np.all(channels.note == FREE_PARTIAL)


def test_a_sound_holding_no_partial_holds_no_channel() -> None:
    channels = channelize(tracks_of(np.random.default_rng(6).normal(size=times().shape[0])), settings=SETTINGS)

    assert channels.channel_count == 0
    assert channels.note_count == 0
