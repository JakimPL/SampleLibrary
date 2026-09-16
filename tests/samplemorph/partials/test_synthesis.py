from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.synthesis import (
    BLOCK_SAMPLES,
    LOWEST_HEARD_HZ,
    NYQUIST_TAPER_END,
    QUIET_PARTIAL_DB,
    oscillate,
)
from samplemorph.partials.tracks import PartialTracks
from tests.samplemorph.partials.conftest import HOP_LENGTH, RATE_HZ

AMPLITUDE: Final[float] = 0.4
STEADY_HZ: Final[float] = 440.0
LONG_SAMPLES: Final[int] = 3 * BLOCK_SAMPLES
FREQUENCY_TOLERANCE_HZ: Final[float] = 0.5
AMPLITUDE_TOLERANCE: Final[float] = 0.005
GLIDE_SHARE_CEILING: Final[float] = 1e-6
SINGLE_PRECISION_TOLERANCE: Final[float] = 1e-7
SILENT_LEVEL: Final[float] = 1e-12


def _tracks(frequency_hz: NDArray[np.float64], amplitude: NDArray[np.float64]) -> PartialTracks:
    return PartialTracks(
        frequency_hz=np.atleast_2d(frequency_hz).astype(np.float32),
        amplitude=np.atleast_2d(amplitude).astype(np.float32),
        hop_length=HOP_LENGTH,
        rate_hz=RATE_HZ,
    )


def _held(value: float, *, sample_count: int) -> NDArray[np.float64]:
    return np.full(1 + sample_count // HOP_LENGTH, value)


def _loudest_hz(waveform: NDArray[np.float64]) -> float:
    spectrum = np.abs(np.fft.rfft(waveform * np.hanning(waveform.shape[0])))
    return float(np.fft.rfftfreq(waveform.shape[0], 1.0 / RATE_HZ)[int(np.argmax(spectrum))])


def test_a_steady_partial_sounds_at_its_own_frequency_and_amplitude() -> None:
    tracks = _tracks(_held(STEADY_HZ, sample_count=LONG_SAMPLES), _held(AMPLITUDE, sample_count=LONG_SAMPLES))

    waveform = oscillate(tracks, sample_count=LONG_SAMPLES)

    assert waveform.shape[0] == LONG_SAMPLES
    assert abs(_loudest_hz(waveform) - STEADY_HZ) <= FREQUENCY_TOLERANCE_HZ
    assert abs(float(np.abs(waveform).max()) - AMPLITUDE) <= AMPLITUDE_TOLERANCE


def test_a_partial_carries_its_phase_across_every_block_it_sounds_through() -> None:
    """A partial spanning several blocks is the tone one unbroken oscillator makes, read at the precision it is stored in."""
    tracks = _tracks(_held(STEADY_HZ, sample_count=LONG_SAMPLES), _held(AMPLITUDE, sample_count=LONG_SAMPLES))

    waveform = oscillate(tracks, sample_count=LONG_SAMPLES)

    turns = 2.0 * np.pi * STEADY_HZ * (np.arange(LONG_SAMPLES) + 1) / RATE_HZ
    assert np.abs(waveform - AMPLITUDE * np.sin(turns)).max() <= SINGLE_PRECISION_TOLERANCE


def test_a_partial_gliding_past_what_the_rate_carries_fades_out_where_it_stands() -> None:
    sample_count = BLOCK_SAMPLES
    frame_count = 1 + sample_count // HOP_LENGTH
    frequency = np.linspace(0.4 * RATE_HZ, 0.6 * RATE_HZ, frame_count)

    waveform = oscillate(_tracks(frequency, np.full(frame_count, AMPLITUDE)), sample_count=sample_count)

    spectrum = np.abs(np.fft.rfft(waveform * np.hanning(sample_count))) ** 2
    frequencies = np.fft.rfftfreq(sample_count, 1.0 / RATE_HZ)
    folded = spectrum[frequencies < 0.39 * RATE_HZ].sum() / spectrum.sum()
    assert float(folded) <= GLIDE_SHARE_CEILING
    assert float(np.abs(waveform[-sample_count // 8 :]).max()) == 0.0


def test_a_partial_under_what_is_heard_as_pitch_stays_silent() -> None:
    sample_count = BLOCK_SAMPLES
    frame_count = 1 + sample_count // HOP_LENGTH
    low = _tracks(np.full(frame_count, LOWEST_HEARD_HZ / 2.0), np.full(frame_count, AMPLITUDE))

    assert float(np.abs(oscillate(low, sample_count=sample_count)).max()) == 0.0


def test_a_partial_far_under_the_loudest_is_left_out() -> None:
    sample_count = BLOCK_SAMPLES
    frame_count = 1 + sample_count // HOP_LENGTH
    quiet = AMPLITUDE * 10.0 ** (-(QUIET_PARTIAL_DB + 20.0) / 20.0)
    frequency = np.stack((np.full(frame_count, STEADY_HZ), np.full(frame_count, 3.0 * STEADY_HZ)))
    amplitude = np.stack((np.full(frame_count, AMPLITUDE), np.full(frame_count, quiet)))

    both = oscillate(_tracks(frequency, amplitude), sample_count=sample_count)
    loudest_alone = oscillate(_tracks(frequency[:1], amplitude[:1]), sample_count=sample_count)

    assert np.array_equal(both, loudest_alone)


def test_a_sound_with_no_partial_is_silence() -> None:
    empty = PartialTracks(
        frequency_hz=np.zeros((0, 8), dtype=np.float32),
        amplitude=np.zeros((0, 8), dtype=np.float32),
        hop_length=HOP_LENGTH,
        rate_hz=RATE_HZ,
    )

    assert not np.any(oscillate(empty, sample_count=1024))


def test_a_partial_born_partway_through_sounds_from_where_it_starts() -> None:
    sample_count = 2 * BLOCK_SAMPLES
    frame_count = 1 + sample_count // HOP_LENGTH
    amplitude = np.where(np.arange(frame_count) >= frame_count // 2, AMPLITUDE, 0.0)

    waveform = oscillate(_tracks(np.full(frame_count, STEADY_HZ), amplitude), sample_count=sample_count)

    assert float(np.abs(waveform[: sample_count // 2 - HOP_LENGTH]).max()) <= SILENT_LEVEL
    assert abs(float(np.abs(waveform[-sample_count // 4 :]).max()) - AMPLITUDE) <= AMPLITUDE_TOLERANCE
    assert float(np.abs(np.diff(waveform)).max()) <= 2.0 * np.pi * NYQUIST_TAPER_END * AMPLITUDE
