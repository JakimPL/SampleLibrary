from __future__ import annotations

import numpy as np
import pytest

from samplemorph.geometry import Anchor, log_frequency_geometry
from samplemorph.measurement.ladders.axis import MINIMUM_BINS_PER_SEMITONE, PooledAxis
from tests.samplemorph.measurement.ladders.conftest import AXIS, GEOMETRY


def _semitone_width_in_bins(band: int) -> float:
    return float(
        AXIS.band_frequencies[band] * (2.0 ** (1.0 / 12.0) - 1.0) / (GEOMETRY.analysis_rate_hz / GEOMETRY.fft_length)
    )


def test_the_trusted_bands_begin_where_a_semitone_spans_enough_bins_to_tell_partials_apart() -> None:
    lowest = AXIS.lowest_resolved_band

    assert _semitone_width_in_bins(lowest) >= MINIMUM_BINS_PER_SEMITONE
    assert _semitone_width_in_bins(lowest - 1) < MINIMUM_BINS_PER_SEMITONE


def test_a_pooled_band_stands_about_one_semitone_above_the_one_below() -> None:
    """The fine bands do not divide evenly into the pooled ones, so a span holds 23 or 24 of the 24 in a semitone."""
    steps = np.diff(12.0 * np.log2(AXIS.band_frequencies))

    assert np.allclose(steps, 1.0, atol=1.0 / 24.0)


@pytest.mark.parametrize("interval", (3.0, 12.0))
def test_a_ladder_is_read_without_the_top_bands_its_interval_reaches(interval: float) -> None:
    unmoved = AXIS.reading_bands(interval_semitones=0.0)
    moved = AXIS.reading_bands(interval_semitones=interval)

    assert unmoved.sum() - moved.sum() == int(interval)
    assert not moved[-int(interval) :].any()
    assert not moved[: AXIS.lowest_resolved_band].any()


def test_an_aligned_geometry_is_refused() -> None:
    with pytest.raises(ValueError, match="unaligned"):
        PooledAxis(geometry=log_frequency_geometry(anchor=Anchor.LOUDEST), band_count=113, bands_per_semitone=1)
