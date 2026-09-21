from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
import torch

from sampledescriptor.descriptors.pooling import canonical_duration, pool_bands, pooled_band_count
from sampledescriptor.images import Conditioners
from samplemorph.geometry import log_frequency_geometry


@dataclass(frozen=True)
class PoolCase:
    rows: int
    band_count: int


@pytest.mark.parametrize(
    "case",
    [PoolCase(rows=2507, band_count=209), PoolCase(rows=24, band_count=8), PoolCase(rows=10, band_count=3)],
    ids=lambda case: f"{case.rows}_to_{case.band_count}",
)
def test_pooling_lays_its_spans_out_the_way_adaptive_pooling_does(case: PoolCase) -> None:
    """Training pools with this function and the network was shaped by the same rule, so both must agree."""
    grid = np.random.default_rng(0).random((case.rows, 4))

    pooled = pool_bands(grid, band_count=case.band_count)
    reference = torch.nn.functional.adaptive_avg_pool1d(torch.from_numpy(grid.T)[None], case.band_count)[0].T

    assert pooled.dtype == np.float32
    assert pooled.shape == (case.band_count, 4)
    np.testing.assert_allclose(pooled, reference.numpy(), rtol=1e-5)


def test_the_default_grid_pools_to_one_band_per_semitone() -> None:
    geometry = log_frequency_geometry()

    band_count = pooled_band_count(geometry, bands_per_semitone=1)

    assert band_count == -(-geometry.grid_shape[0] // round(geometry.bands_per_semitone))


def test_a_grid_coarser_than_the_pooling_is_refused() -> None:
    geometry = log_frequency_geometry()

    with pytest.raises(ValueError, match="cannot be pooled"):
        pooled_band_count(geometry, bands_per_semitone=round(geometry.bands_per_semitone) + 1)


def test_the_canonical_duration_stays_put_under_a_retuning() -> None:
    """Reading a sound an octave up raises its translation by twelve and halves its duration."""
    stored = Conditioners(translation_semitones=3.0, log_duration=-1.0, log_gain=0.0)
    retuned = Conditioners(translation_semitones=15.0, log_duration=-2.0, log_gain=0.0)

    assert canonical_duration(stored) == pytest.approx(canonical_duration(retuned))
