from __future__ import annotations

import numpy as np

from samplemorph.measurement.phase_quality import phase_quality

RATE_HZ = 44100
DURATION_SECONDS = 0.5
FLUTTER_RATE_HZ = 6.0
FLUTTER_DEPTH = 0.5


def _tone(frequency_hz: float) -> np.ndarray:
    times = np.arange(int(RATE_HZ * DURATION_SECONDS)) / RATE_HZ
    return np.sin(2 * np.pi * frequency_hz * times)


def test_a_reconstruction_identical_to_the_reference_reads_as_no_difference() -> None:
    reference = _tone(440.0)

    quality = phase_quality(reference.copy(), reference)

    assert quality.magnitude_distance < 1e-6
    assert quality.modulation_excess < 1e-6


def test_a_reconstruction_fluttering_over_a_steady_reference_reads_positive_modulation_excess() -> None:
    """A comb swept through a held note is amplitude flutter the steady reference has none of."""
    reference = _tone(440.0)
    times = np.arange(reference.size) / RATE_HZ
    fluttered = reference * (1.0 + FLUTTER_DEPTH * np.sin(2 * np.pi * FLUTTER_RATE_HZ * times))

    quality = phase_quality(fluttered, reference)

    assert quality.modulation_excess > 0.0
