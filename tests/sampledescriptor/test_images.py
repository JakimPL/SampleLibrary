from __future__ import annotations

import numpy as np
import pytest

from sampledescriptor.images import Conditioners, SoundImage
from samplemorph.geometry import log_frequency_geometry

CONDITIONERS = Conditioners(translation_semitones=0.0, log_duration=-2.0, log_gain=-1.0)


def _grid(geometry: object, *, fill: float = 0.5) -> np.ndarray:
    return np.full(geometry.grid_shape, fill)  # type: ignore[attr-defined]


def test_a_sound_image_reports_its_own_grid_extent() -> None:
    geometry = log_frequency_geometry()

    image = SoundImage(grid=_grid(geometry), conditioners=CONDITIONERS, geometry=geometry)

    assert (image.band_count, image.time_columns) == geometry.grid_shape


def test_a_sound_image_rejects_a_grid_the_geometry_does_not_describe() -> None:
    geometry = log_frequency_geometry()

    with pytest.raises(ValueError, match="geometry asks for"):
        SoundImage(grid=np.zeros((3, 4)), conditioners=CONDITIONERS, geometry=geometry)


def test_a_sound_image_rejects_a_grid_carrying_values_that_are_not_finite() -> None:
    geometry = log_frequency_geometry()
    grid = _grid(geometry)
    grid[0, 0] = np.nan

    with pytest.raises(ValueError, match="finite"):
        SoundImage(grid=grid, conditioners=CONDITIONERS, geometry=geometry)


def test_a_sound_image_rejects_a_grid_reaching_outside_the_unit_range() -> None:
    geometry = log_frequency_geometry()

    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        SoundImage(grid=_grid(geometry, fill=1.5), conditioners=CONDITIONERS, geometry=geometry)
