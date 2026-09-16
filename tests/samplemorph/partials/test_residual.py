from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import analysis_transform, prepare_mono
from tests.samplemorph.partials.conftest import GEOMETRY, RATE_HZ, harmonics, model_of, noise_hit, times

FUNDAMENTAL_HZ: Final[float] = 440.0
HARMONIC_COUNT: Final[int] = 6
SIGNAL_TO_NOISE_DB: Final[float] = 20.0
NEAR_BINS: Final[float] = 3.0
FAR_BINS: Final[float] = 10.0
FLOOR_HEADROOM_DB: Final[float] = 3.0
BIN_SPACING_HZ: Final[float] = RATE_HZ / GEOMETRY.fft_length


def _energy(waveform: NDArray[np.float64]) -> NDArray[np.float32]:
    energy: NDArray[np.float32] = (np.abs(analysis_transform(prepare_mono(waveform), geometry=GEOMETRY)) ** 2).astype(
        np.float32
    )
    return energy


def _distance_bins() -> NDArray[np.float64]:
    """How many bins each bin stands from the nearest harmonic."""
    bins = np.arange(GEOMETRY.fft_length // 2 + 1)
    harmonic_bins = np.arange(1, HARMONIC_COUNT + 1) * FUNDAMENTAL_HZ / BIN_SPACING_HZ
    return np.abs(bins[:, None] - harmonic_bins).min(axis=1)


def test_a_tone_over_noise_leaves_the_noise_where_it_stands_and_takes_the_partials_out() -> None:
    noise = 0.5 * np.random.default_rng(13).normal(size=times().shape[0])
    tone = harmonics(FUNDAMENTAL_HZ, harmonic_count=HARMONIC_COUNT)
    quiet_noise = noise * float(np.sqrt(np.mean(tone**2) / np.mean(noise**2))) * 10.0 ** (-SIGNAL_TO_NOISE_DB / 20.0)

    residual = model_of(tone + quiet_noise).residual.energy

    distance = _distance_bins()
    floor = float(np.median(_energy(quiet_noise)[distance <= NEAR_BINS]))
    assert float(np.median(residual[distance <= NEAR_BINS])) <= floor * 10.0 ** (FLOOR_HEADROOM_DB / 10.0)
    assert np.array_equal(residual[distance >= FAR_BINS], _energy(tone + quiet_noise)[distance >= FAR_BINS])


def test_a_sound_holding_no_partial_keeps_every_bin_of_its_energy() -> None:
    model = model_of(noise_hit(seed=4))

    assert model.partials.track_count == 0
    assert model.residual.energy is model.whole.energy


def test_a_tone_leaves_almost_nothing_behind() -> None:
    model = model_of(harmonics(FUNDAMENTAL_HZ, harmonic_count=HARMONIC_COUNT))

    left = float(model.residual.energy.sum()) / float(model.whole.energy.sum())
    assert model.partials.track_count == HARMONIC_COUNT
    assert left <= 0.01
