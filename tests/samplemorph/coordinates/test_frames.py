from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.coordinates.frames import constant_q_frames, frame_analysis
from samplemorph.tones import HarmonicTone, harmonic_tone

RATE_HZ = 44100.0
ANALYSIS = frame_analysis()
TONE = HarmonicTone(fundamental_hz=220.0, resonance_hz=1500.0, seconds=0.7)
LOUD_BIN = 0.7
QUIET_BIN = 0.3
QUIETER_DB = 25.0
FLOOR_TOLERANCE = 0.02


def _bin_of(frequency_hz: float) -> int:
    return int(round(ANALYSIS.bins_per_octave * np.log2(frequency_hz / ANALYSIS.minimum_frequency_hz)))


def _profile(mono: NDArray[np.float64]) -> NDArray[np.float32]:
    return constant_q_frames(prepare_mono(mono), analysis=ANALYSIS).mean(axis=0)


def _best_lag(first: NDArray[np.float32], second: NDArray[np.float32], *, reach: int) -> int:
    lags = range(-reach, reach + 1)
    scores = [
        float(np.dot(first[max(0, -lag) : first.size - max(0, lag)], second[max(0, lag) : second.size - max(0, -lag)]))
        for lag in lags
    ]
    return lags[int(np.argmax(scores))]


def test_a_tone_s_frames_light_its_series_and_leave_the_bins_between_dark() -> None:
    profile = _profile(harmonic_tone(TONE, rate_hz=RATE_HZ))

    assert all(profile[_bin_of(harmonic * 220.0)] > LOUD_BIN for harmonic in (1, 2, 3))
    assert all(profile[_bin_of(between * 220.0)] < QUIET_BIN for between in (1.5, 2.5))


def test_a_tone_retuned_by_semitones_moves_its_frames_by_three_bins_each() -> None:
    waveform = harmonic_tone(TONE, rate_hz=RATE_HZ)

    moved = _best_lag(
        _profile(waveform), _profile(resample_by_semitones(waveform, semitones=5.0)), reach=int(ANALYSIS.band_count / 4)
    )

    assert moved == 5 * int(ANALYSIS.bins_per_semitone)


def test_a_quiet_frame_is_read_no_deeper_than_the_sample_s_floor() -> None:
    """A sine held loud and then 25 dB quieter: the quiet frames keep their bins down to 70 dB under the loud ones."""
    times = np.arange(int(RATE_HZ / 2)) / RATE_HZ
    sine = np.sin(2.0 * np.pi * 440.0 * times)
    stepped = np.concatenate([sine, 10.0 ** (-QUIETER_DB / 20.0) * sine])

    frames = constant_q_frames(prepare_mono(stepped[:, None]), analysis=ANALYSIS)

    loud, quiet = frames[: frames.shape[0] // 2], frames[frames.shape[0] // 2 :]
    lowest_quiet = (QUIETER_DB + ANALYSIS.frame_range_db - ANALYSIS.sample_range_db) / ANALYSIS.frame_range_db
    assert float(loud[loud > 0.0].min()) < lowest_quiet / 2.0
    assert all(float(frame[frame > 0.0].min()) >= lowest_quiet - FLOOR_TOLERANCE for frame in quiet)


def test_a_silent_sound_keeps_no_frames_and_a_short_one_keeps_what_it_has() -> None:
    silent = constant_q_frames(PreparedMono(np.zeros(4096)), analysis=ANALYSIS)
    short = constant_q_frames(
        prepare_mono(
            harmonic_tone(HarmonicTone(fundamental_hz=440.0, resonance_hz=2000.0, seconds=0.05), rate_hz=RATE_HZ)
        ),
        analysis=ANALYSIS,
    )

    assert silent.shape == (0, ANALYSIS.band_count)
    assert 0 < short.shape[0] < ANALYSIS.kept_frame_count
    assert short.dtype == np.float32
    assert float(short.min()) >= 0.0 and float(short.max()) == 1.0
