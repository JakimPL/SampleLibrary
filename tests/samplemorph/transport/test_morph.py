from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import TransportedSpectrogram, transport, transport_along
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import build_time_map
from samplemorph.vocoders.pghi import integrate_and_synthesize
from tests.samplemorph.transport.conftest import (
    BIN_SPACING_HZ,
    CLIP_FRAMES,
    GEOMETRY,
    analysis_of,
    decaying,
    middle_spectrum,
    noise_band,
    sines,
    tone,
)

HOP = GEOMETRY.hop_length
MIDPOINT: Final[float] = 0.5
LOW_TONE_HZ: Final[float] = 220.0
HIGH_TONE_HZ: Final[float] = 330.0
SERIES_REACH_BINS: Final[float] = 2.0
SERIES_SHARE_FLOOR: Final[float] = 0.9
PEAK_REACH_BINS: Final[float] = 2.0
BAND_MARGIN_OCTAVES: Final[float] = 1.0 / 6.0
BAND_SHARE_FLOOR: Final[float] = 0.8
LEVEL_TOLERANCE_DB: Final[float] = 1.0
CONTINUITY_WEIGHT: Final[float] = 1e-3
CONTINUITY_CEILING: Final[float] = 0.05
BLEND_RATIO_FLOOR: Final[float] = 0.5
ONSET_RISE_DB: Final[float] = 12.0
ONSET_LOOKBACK_FRAMES: Final[int] = 7
DECAY_FLOOR_DB: Final[float] = 40.0
PITCH_TOLERANCE: Final[float] = 0.03


def _transport(first: TransportAnalysis, second: TransportAnalysis, weight: float) -> TransportedSpectrogram:
    return transport(first, second, weight=weight, geometry=GEOMETRY, settings=TransportSettings())


def _blend(first: TransportAnalysis, second: TransportAnalysis, weight: float) -> TransportedSpectrogram:
    return blend(
        first,
        second,
        weight=weight,
        geometry=GEOMETRY,
        settings=TransportSettings(),
    )


def _series_share(spectrum: NDArray[np.float64], fundamental_hz: float, harmonic_count: int) -> float:
    bins = np.arange(spectrum.shape[0])
    near = np.zeros(spectrum.shape[0], dtype=bool)
    for harmonic in range(1, harmonic_count + 1):
        near |= np.abs(bins - harmonic * fundamental_hz / BIN_SPACING_HZ) <= SERIES_REACH_BINS
    return float(spectrum[near].sum() / spectrum.sum())


def _frame_decibels(spectrogram: TransportedSpectrogram) -> NDArray[np.float64]:
    energy = (spectrogram.magnitude.astype(np.float64) ** 2).sum(axis=0)
    decibels: NDArray[np.float64] = 10.0 * np.log10(np.maximum(energy, 1e-30) / energy.max())
    return decibels


@pytest.fixture(scope="module")
def low_tone() -> TransportAnalysis:
    return analysis_of(tone(LOW_TONE_HZ))


@pytest.fixture(scope="module")
def high_tone() -> TransportAnalysis:
    return analysis_of(tone(HIGH_TONE_HZ))


def test_the_ends_are_each_sound_s_own_analysis(low_tone: TransportAnalysis, high_tone: TransportAnalysis) -> None:
    first_end = _transport(low_tone, high_tone, 0.0)
    second_end = _transport(low_tone, high_tone, 1.0)

    assert np.array_equal(first_end.magnitude, np.sqrt(low_tone.energy))
    assert first_end.sample_count == low_tone.sample_count
    assert np.array_equal(second_end.magnitude, np.sqrt(high_tone.energy))


def test_a_transport_is_what_it_carries_along_the_map_it_builds(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    """A morph aligning two sounds by more than their spectra builds the map itself and sends the rest along it."""
    time_map = build_time_map(low_tone, high_tone, weight=MIDPOINT, hop_length=HOP, settings=TransportSettings())

    along = transport_along(low_tone, high_tone, time_map=time_map, weight=MIDPOINT, settings=TransportSettings())

    whole = _transport(low_tone, high_tone, MIDPOINT)
    assert np.array_equal(along.magnitude, whole.magnitude)
    assert along.sample_count == whole.sample_count


def test_a_point_just_past_an_end_sounds_like_that_end(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    near = _transport(low_tone, high_tone, CONTINUITY_WEIGHT).magnitude.astype(np.float64)
    end = np.sqrt(low_tone.energy.astype(np.float64))

    assert near.shape == end.shape
    assert np.sqrt(np.mean((near - end) ** 2)) / np.sqrt(np.mean(end**2)) < CONTINUITY_CEILING


def test_a_path_read_backward_is_the_same_path(low_tone: TransportAnalysis, high_tone: TransportAnalysis) -> None:
    forward = _transport(low_tone, high_tone, 0.25).magnitude
    backward = _transport(high_tone, low_tone, 0.75).magnitude

    assert np.allclose(forward, backward, rtol=1e-4, atol=1e-6 * float(forward.max()))


def test_a_sound_morphed_with_itself_stays_itself(low_tone: TransportAnalysis) -> None:
    itself = _transport(low_tone, low_tone, MIDPOINT).magnitude
    own = np.sqrt(low_tone.energy)

    assert np.allclose(itself, own, rtol=1e-3, atol=1e-6 * float(own.max()))


def test_the_gain_of_an_end_moves_only_the_level_of_the_path(high_tone: TransportAnalysis) -> None:
    quiet = analysis_of(tone(LOW_TONE_HZ))
    loud = analysis_of(4.0 * tone(LOW_TONE_HZ))

    quiet_path = _transport(quiet, high_tone, MIDPOINT).magnitude.astype(np.float64) ** 2
    loud_path = _transport(loud, high_tone, MIDPOINT).magnitude.astype(np.float64) ** 2

    quiet_shapes = quiet_path / quiet_path.sum(axis=0)
    loud_shapes = loud_path / loud_path.sum(axis=0)
    assert np.allclose(quiet_shapes, loud_shapes, rtol=1e-3, atol=1e-9)
    assert float(loud_path.sum()) > float(quiet_path.sum())


def test_a_tone_glides_to_the_geometric_pitch_between_its_ends(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    between_hz = float(np.sqrt(LOW_TONE_HZ * HIGH_TONE_HZ))

    transported = middle_spectrum(_transport(low_tone, high_tone, MIDPOINT).magnitude)
    blended = middle_spectrum(_blend(low_tone, high_tone, MIDPOINT).magnitude)

    assert _series_share(transported, between_hz, harmonic_count=4) >= SERIES_SHARE_FLOOR
    assert _series_share(blended, between_hz, harmonic_count=4) < 1.0 - SERIES_SHARE_FLOOR


def test_the_notes_of_a_chord_travel_in_order() -> None:
    first = analysis_of(sines((300.0, 500.0)))
    second = analysis_of(sines((400.0, 800.0)))

    spectrum = middle_spectrum(_transport(first, second, MIDPOINT).magnitude)

    peaks = np.flatnonzero((spectrum[1:-1] > spectrum[:-2]) & (spectrum[1:-1] >= spectrum[2:])) + 1
    loudest = np.sort(peaks[np.argsort(spectrum[peaks])[-2:]]) * BIN_SPACING_HZ
    expected = np.array([np.sqrt(300.0 * 400.0), np.sqrt(500.0 * 800.0)])
    assert np.all(np.abs(loudest - expected) <= PEAK_REACH_BINS * BIN_SPACING_HZ)


def test_a_band_of_noise_slides_to_the_geometric_band_between_its_ends() -> None:
    first = analysis_of(noise_band(500.0, 1000.0, seed=3))
    second = analysis_of(noise_band(2000.0, 4000.0, seed=4))

    spectrum = middle_spectrum(_transport(first, second, MIDPOINT).magnitude)

    frequencies = np.arange(spectrum.shape[0]) * BIN_SPACING_HZ
    margin = 2.0**BAND_MARGIN_OCTAVES
    inside = (frequencies >= 1000.0 / margin) & (frequencies <= 2000.0 * margin)
    assert spectrum[inside].sum() / spectrum.sum() >= BAND_SHARE_FLOOR


def test_a_decay_between_a_fast_and_a_slow_one_falls_at_a_rate_between_theirs() -> None:
    frame_count = CLIP_FRAMES
    fast = analysis_of(decaying(tone(440.0, frame_count=frame_count), time_constant_seconds=0.03))
    slow = analysis_of(decaying(tone(440.0, frame_count=frame_count), time_constant_seconds=0.3))

    rates = [_decay_rate(_transport(fast, slow, weight)) for weight in (0.0, MIDPOINT, 1.0)]

    assert rates[0] > rates[1] > rates[2]


def _decay_rate(spectrogram: TransportedSpectrogram) -> float:
    """Decibels lost per second from the loudest frame down to `DECAY_FLOOR_DB` under it."""
    decibels = _frame_decibels(spectrogram)
    peak = int(np.argmax(decibels))
    fallen = np.flatnonzero(decibels[peak:] < -DECAY_FLOOR_DB)
    last = peak + (int(fallen[0]) if fallen.size else decibels.shape[0] - peak - 1)
    seconds = (last - peak) * HOP / NOMINAL_WAV_RATE
    return float((decibels[peak] - decibels[last]) / seconds)


def test_two_hits_apart_in_time_meet_as_one_attack_between_them() -> None:
    delay_seconds = 0.1
    early = analysis_of(decaying(tone(440.0), time_constant_seconds=1.0 / 30.0))
    late = analysis_of(decaying(tone(440.0), time_constant_seconds=1.0 / 30.0, delay_seconds=delay_seconds))

    decibels = _frame_decibels(_transport(early, late, MIDPOINT))

    rises = decibels[ONSET_LOOKBACK_FRAMES:] - decibels[:-ONSET_LOOKBACK_FRAMES]
    climbing = np.concatenate(([0], (rises >= ONSET_RISE_DB).astype(np.int8)))
    assert np.count_nonzero(np.diff(climbing) == 1) == 1
    attack_seconds = int(np.flatnonzero(decibels >= -ONSET_RISE_DB)[0]) * HOP / NOMINAL_WAV_RATE
    assert 0.0 < attack_seconds < delay_seconds


def test_the_length_between_two_sounds_is_the_geometric_length() -> None:
    short = analysis_of(tone(440.0, frame_count=4096))
    long = analysis_of(tone(440.0, frame_count=16384))

    between = _transport(short, long, MIDPOINT)

    assert between.sample_count == 8192
    assert between.magnitude.shape[1] == 1 + 8192 // HOP


def test_two_sounds_of_one_level_keep_that_level_all_the_way(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    end_level = float(np.median(low_tone.frame_energy))

    for weight in (0.25, MIDPOINT, 0.75):
        energy = (_transport(low_tone, high_tone, weight).magnitude.astype(np.float64) ** 2).sum(axis=0)
        middle = energy[energy.shape[0] // 4 : 3 * energy.shape[0] // 4]
        assert np.all(np.abs(10.0 * np.log10(middle / end_level)) <= LEVEL_TOLERANCE_DB)


def test_the_midpoint_stands_far_from_the_crossfade_of_its_ends(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    first = _decibels(middle_spectrum(np.sqrt(low_tone.energy)))
    second = _decibels(middle_spectrum(np.sqrt(high_tone.energy)))
    transported = _decibels(middle_spectrum(_transport(low_tone, high_tone, MIDPOINT).magnitude))
    blended = _decibels(middle_spectrum(_blend(low_tone, high_tone, MIDPOINT).magnitude))

    ends_apart = np.sqrt(np.mean((first - second) ** 2))
    assert np.sqrt(np.mean((transported - blended) ** 2)) / ends_apart >= BLEND_RATIO_FLOOR


def _decibels(spectrum: NDArray[np.float64]) -> NDArray[np.float64]:
    decibels: NDArray[np.float64] = 10.0 * np.log10(np.maximum(spectrum / spectrum.max(), 1e-8))
    return decibels


def test_a_rendered_midpoint_sounds_at_the_pitch_between_its_ends(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    between = _transport(low_tone, high_tone, MIDPOINT)

    waveform = integrate_and_synthesize(between.magnitude, geometry=GEOMETRY, frame_count=between.sample_count)

    middle = waveform[waveform.shape[0] // 4 : 3 * waveform.shape[0] // 4]
    spectrum = np.abs(np.fft.rfft(middle * np.hanning(middle.shape[0])))
    frequencies = np.fft.rfftfreq(middle.shape[0], 1.0 / NOMINAL_WAV_RATE)
    loudest_hz = float(frequencies[np.argmax(spectrum)])
    assert loudest_hz == pytest.approx(np.sqrt(LOW_TONE_HZ * HIGH_TONE_HZ), rel=PITCH_TOLERANCE)


@dataclass(frozen=True)
class EdgeCase:
    name: str
    first: NDArray[np.float64]
    second: NDArray[np.float64]


EDGE_CASES = (
    EdgeCase("both silent", np.zeros(8192), np.zeros(8192)),
    EdgeCase("a sound shorter than one transform", tone(440.0, frame_count=300), tone(660.0, frame_count=8192)),
    EdgeCase("two sounds of one frame", tone(440.0, frame_count=100), tone(660.0, frame_count=100)),
)


@pytest.mark.parametrize("case", EDGE_CASES, ids=lambda case: case.name)
def test_silent_and_very_short_sounds_still_travel(case: EdgeCase) -> None:
    between = _transport(analysis_of(case.first), analysis_of(case.second), MIDPOINT)

    assert np.all(np.isfinite(between.magnitude))
    assert between.magnitude.shape[1] == 1 + between.sample_count // HOP


def test_a_sound_meeting_silence_fades_through_it(high_tone: TransportAnalysis) -> None:
    silence = analysis_of(np.zeros(CLIP_FRAMES))

    energy = (_transport(silence, high_tone, MIDPOINT).magnitude.astype(np.float64) ** 2).sum(axis=0)

    middle = energy[energy.shape[0] // 4 : 3 * energy.shape[0] // 4]
    assert np.all(middle > 0.0)
    assert np.all(10.0 * np.log10(middle / float(np.median(high_tone.frame_energy))) > -12.0)


@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_a_weight_outside_the_path_is_refused(
    weight: float, low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        _transport(low_tone, high_tone, weight)
