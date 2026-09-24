from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from sampledescriptor.descriptors.grid_descriptor import GridDescriptor
from sampledescriptor.descriptors.learned import DescriptorDescription, save_descriptor
from sampledescriptor.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE, pooled_band_count
from sampledescriptor.descriptors.shape import DescriptorShape
from sampledescriptor.geometry import grid_geometry
from sampledescriptor.model_paths import descriptor_path

TINY_EMBEDDING_SIZE: Final[int] = 16


@pytest.fixture
def descriptor_shape() -> DescriptorShape:
    geometry = grid_geometry()
    return DescriptorShape(
        band_count=pooled_band_count(geometry, bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE),
        time_columns=geometry.time_columns,
        width=4,
        stage_count=2,
        embedding_size=TINY_EMBEDDING_SIZE,
    )


@pytest.fixture
def descriptor_description(descriptor_shape: DescriptorShape) -> DescriptorDescription:
    return DescriptorDescription(
        canonicalizer="log_frequency",
        geometry=grid_geometry(),
        bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE,
        shape=descriptor_shape,
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=8,
        best_validation_loss=0.5,
    )


@pytest.fixture
def stored_descriptor(tmp_path: Path, descriptor_description: DescriptorDescription) -> Path:
    """A tiny untrained descriptor saved the way training saves one."""
    path = descriptor_path(tmp_path / "trained", name="tiny")
    save_descriptor(path, GridDescriptor(descriptor_description.shape).eval(), descriptor_description)
    return path
