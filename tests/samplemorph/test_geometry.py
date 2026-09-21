from __future__ import annotations

import numpy as np
import pytest

from samplemorph.geometry import SEMITONES_PER_OCTAVE, log_frequency_geometry


def test_the_band_frequencies_rise_across_the_axis() -> None:
    geometry = log_frequency_geometry()

    frequencies = geometry.band_frequencies

    assert frequencies.shape == (geometry.band_count,)
    assert np.all(np.diff(frequencies) > 0.0)


def test_a_logarithmic_axis_spaces_every_octave_by_the_same_band_count() -> None:
    """An exactly logarithmic axis is what makes a rate change a whole-band translation."""
    geometry = log_frequency_geometry()
    frequencies = geometry.band_frequencies
    octave_steps = np.log2(frequencies[1:] / frequencies[:-1]) * geometry.bins_per_octave

    assert np.allclose(octave_steps, 1.0)
    assert geometry.bins_per_octave / SEMITONES_PER_OCTAVE > 0.0


def test_the_log_frequency_bands_reach_every_fourier_bin_the_analysis_produces() -> None:
    """Synthesis reads each Fourier bin from a band that measured it.

    A sample stored at the nominal rate plays back far below it, so the top of the analyzed range
    lands within hearing and has to carry content rather than silence.
    """
    geometry = log_frequency_geometry()

    assert geometry.band_frequencies[-1] >= geometry.analysis_rate_hz / 2
