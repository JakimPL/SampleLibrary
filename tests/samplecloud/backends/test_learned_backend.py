from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from samplecloud.backends.learned_backend import build_learned_extractor
from samplemorph.descriptors.grid_descriptor import DescriptorShape, GridDescriptor
from samplemorph.descriptors.learned import DescriptorDescription, descriptor_path, save_descriptor
from samplemorph.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE, pooled_band_count
from samplemorph.geometry import log_frequency_geometry

EMBEDDING_SIZE = 8


def test_a_stored_descriptor_serves_as_an_extractor_by_name(tmp_path: Path) -> None:
    geometry = log_frequency_geometry()
    shape = DescriptorShape(
        band_count=pooled_band_count(geometry, bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE),
        time_columns=geometry.time_columns,
        width=4,
        stage_count=2,
        embedding_size=EMBEDDING_SIZE,
    )
    description = DescriptorDescription(
        canonicalizer="log_frequency",
        geometry=geometry,
        bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE,
        shape=shape,
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=8,
        best_validation_loss=0.5,
    )
    save_descriptor(descriptor_path(tmp_path, name="tiny"), GridDescriptor(shape), description)

    extractor = build_learned_extractor(tmp_path, model_name="tiny", device="cpu")

    vector = extractor.extract(np.sin(np.linspace(0.0, 400.0, 5000))[:, None])
    assert vector.shape == (EMBEDDING_SIZE,)
    assert isinstance(torch.from_numpy(vector), torch.Tensor)
