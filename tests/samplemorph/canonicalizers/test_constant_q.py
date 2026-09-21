from __future__ import annotations

import librosa
import numpy as np
import pytest

from samplemorph.canonicalizers.constant_q import CONSTANT_Q_WINDOW, constant_q_band_count

RATE_HZ = 44100
MINIMUM_FREQUENCY_HZ = 32.70
BINS_PER_OCTAVE = 36


def _builds(band_count: int, *, filter_scale: float) -> bool:
    try:
        librosa.cqt(
            np.zeros(RATE_HZ),
            sr=RATE_HZ,
            fmin=MINIMUM_FREQUENCY_HZ,
            bins_per_octave=BINS_PER_OCTAVE,
            n_bins=band_count,
            filter_scale=filter_scale,
            window=CONSTANT_Q_WINDOW,
        )
    except librosa.util.exceptions.ParameterError:
        return False
    return True


@pytest.mark.parametrize("filter_scale", [1.0, 0.5, 0.25])
def test_the_band_count_is_the_largest_librosa_builds_under_nyquist(filter_scale: float) -> None:
    band_count = constant_q_band_count(
        analysis_rate_hz=RATE_HZ,
        minimum_frequency_hz=MINIMUM_FREQUENCY_HZ,
        bins_per_octave=BINS_PER_OCTAVE,
        filter_scale=filter_scale,
    )

    assert _builds(band_count, filter_scale=filter_scale)
    assert not _builds(band_count + 1, filter_scale=filter_scale)
