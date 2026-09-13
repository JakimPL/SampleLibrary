from __future__ import annotations

import numpy as np
import pytest

from samplecore.auditory.filterbank import analytic_subbands, design_gammatone_bank, erb_frequency_hz, erb_rate

CONTAINER_RATE_HZ = 44100
LOW_HEARD_RATE_HZ = 8363
TONE_SECONDS = 1.0
PROBE_FREQUENCY_HZ = 1000.0
CENTER_CHANNEL = 10
UNIT_GAIN_TOLERANCE = 0.05


def _tone(frequency_hz: float, *, sample_rate_hz: int) -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * sample_rate_hz)) / sample_rate_hz
    return np.cos(2.0 * np.pi * frequency_hz * times)


def _steady_part(values: np.ndarray) -> np.ndarray:
    quarter = values.shape[-1] // 4
    return values[..., quarter:-quarter]


def test_the_erb_scale_inverts_itself() -> None:
    frequencies = np.array([50.0, 440.0, 4000.0, 16000.0])

    assert np.allclose(erb_frequency_hz(erb_rate(frequencies)), frequencies)


@pytest.mark.parametrize("sample_rate_hz", [CONTAINER_RATE_HZ, LOW_HEARD_RATE_HZ])
def test_the_bank_places_rising_centers_below_the_nyquist_frequency(sample_rate_hz: int) -> None:
    bank = design_gammatone_bank(sample_rate_hz=sample_rate_hz)

    assert np.all(np.diff(bank.center_frequencies_hz) > 0.0)
    assert bank.center_frequencies_hz[-1] < sample_rate_hz / 2.0
    assert bank.kernel_cosine.shape == bank.kernel_sine.shape == (bank.channel_count, bank.kernel_length)


def test_a_tone_lands_its_energy_in_the_channel_centered_nearest_it() -> None:
    bank = design_gammatone_bank(sample_rate_hz=CONTAINER_RATE_HZ)
    envelopes = np.abs(analytic_subbands(_tone(PROBE_FREQUENCY_HZ, sample_rate_hz=CONTAINER_RATE_HZ), bank=bank))

    loudest = int(np.argmax(_steady_part(envelopes).mean(axis=-1)))

    assert loudest == int(np.argmin(np.abs(bank.center_frequencies_hz - PROBE_FREQUENCY_HZ)))


def test_a_unit_cosine_at_a_center_reads_an_envelope_of_one() -> None:
    bank = design_gammatone_bank(sample_rate_hz=CONTAINER_RATE_HZ)
    center_hz = float(bank.center_frequencies_hz[CENTER_CHANNEL])
    envelopes = np.abs(analytic_subbands(_tone(center_hz, sample_rate_hz=CONTAINER_RATE_HZ), bank=bank))

    assert _steady_part(envelopes[CENTER_CHANNEL]).mean() == pytest.approx(1.0, abs=UNIT_GAIN_TOLERANCE)


def test_a_rate_too_low_for_the_bank_says_so() -> None:
    with pytest.raises(ValueError, match="highest center"):
        design_gammatone_bank(sample_rate_hz=100)
