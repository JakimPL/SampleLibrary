from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.auditory.envelope import (
    MODULATION_ENVELOPE_RATE_HZ,
    compress,
    decimate,
    local_rms_envelope,
    subband_envelopes,
)
from samplecore.auditory.filterbank import design_gammatone_bank

CONTAINER_RATE_HZ = 44100
TONE_SECONDS = 1.0
CARRIER_HZ = 3000.0
MODULATION_DEPTH = 0.5
STEADY_VARIATION_LIMIT = 0.02
RMS_TOLERANCE = 0.02


@dataclass(frozen=True)
class ModulatedToneCase:
    modulation_hz: float


MODULATED_TONE_CASES = (ModulatedToneCase(modulation_hz=6.0), ModulatedToneCase(modulation_hz=70.0))


def _carrier(sample_rate_hz: int) -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * sample_rate_hz)) / sample_rate_hz
    return np.cos(2.0 * np.pi * CARRIER_HZ * times)


def _modulated(modulation_hz: float, *, sample_rate_hz: int) -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * sample_rate_hz)) / sample_rate_hz
    return _carrier(sample_rate_hz) * (1.0 + MODULATION_DEPTH * np.sin(2.0 * np.pi * modulation_hz * times))


def _steady_part(values: np.ndarray) -> np.ndarray:
    quarter = values.shape[-1] // 4
    return values[..., quarter:-quarter]


def _carrier_channel_envelope(waveform: np.ndarray) -> np.ndarray:
    bank = design_gammatone_bank(sample_rate_hz=CONTAINER_RATE_HZ)
    channel = int(np.argmin(np.abs(bank.center_frequencies_hz - CARRIER_HZ)))
    factor = round(CONTAINER_RATE_HZ / MODULATION_ENVELOPE_RATE_HZ)
    return decimate(compress(subband_envelopes(waveform, bank=bank)), factor=factor)[channel]


def _dominant_modulation_hz(envelope: np.ndarray) -> float:
    steady = _steady_part(envelope)
    spectrum = np.abs(np.fft.rfft((steady - steady.mean()) * np.hanning(steady.shape[0])))
    frequencies = np.fft.rfftfreq(
        steady.shape[0], round(CONTAINER_RATE_HZ / MODULATION_ENVELOPE_RATE_HZ) / CONTAINER_RATE_HZ
    )
    return float(frequencies[int(np.argmax(spectrum))])


def test_the_envelope_of_a_steady_tone_is_flat() -> None:
    steady = _steady_part(_carrier_channel_envelope(_carrier(CONTAINER_RATE_HZ)))

    assert steady.std() / steady.mean() < STEADY_VARIATION_LIMIT


@pytest.mark.parametrize("case", MODULATED_TONE_CASES)
def test_the_envelope_follows_the_modulation_through_decimation(case: ModulatedToneCase) -> None:
    envelope = _carrier_channel_envelope(_modulated(case.modulation_hz, sample_rate_hz=CONTAINER_RATE_HZ))

    resolution_hz = MODULATION_ENVELOPE_RATE_HZ / _steady_part(envelope).shape[0]
    assert _dominant_modulation_hz(envelope) == pytest.approx(case.modulation_hz, abs=2.0 * resolution_hz)


def test_the_local_rms_envelope_of_a_steady_tone_reads_its_rms_level() -> None:
    level = local_rms_envelope(_carrier(CONTAINER_RATE_HZ), sample_rate_hz=CONTAINER_RATE_HZ)

    assert _steady_part(level).mean() == pytest.approx(np.sqrt(0.5), abs=RMS_TOLERANCE)
    assert level.shape == _carrier(CONTAINER_RATE_HZ).shape
    assert np.all(level > 0.0)


def test_the_local_rms_envelope_of_silence_stays_finite_and_positive() -> None:
    level = local_rms_envelope(np.zeros(4096), sample_rate_hz=CONTAINER_RATE_HZ)

    assert np.isfinite(level).all()
    assert np.all(level > 0.0)
