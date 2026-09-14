from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from samplemorph.descriptors.descriptor_shape import DescriptorShape
from samplemorph.descriptors.grid_descriptor import GridDescriptor
from samplemorph.descriptors.learned import DescriptorDescription, load_descriptor, save_descriptor
from samplemorph.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE, pooled_band_count
from samplemorph.geometry import log_frequency_geometry
from samplemorph.model_paths import descriptor_path

EMBEDDING_SIZE = 16


def _description(shape: DescriptorShape) -> DescriptorDescription:
    return DescriptorDescription(
        canonicalizer="log_frequency",
        geometry=log_frequency_geometry(),
        bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE,
        shape=shape,
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=8,
        best_validation_loss=0.5,
    )


def _shape() -> DescriptorShape:
    geometry = log_frequency_geometry()
    return DescriptorShape(
        band_count=pooled_band_count(geometry, bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE),
        time_columns=geometry.time_columns,
        width=4,
        stage_count=2,
        embedding_size=EMBEDDING_SIZE,
    )


def test_the_network_answers_with_one_unit_vector_per_grid() -> None:
    shape = _shape()
    model = GridDescriptor(shape)

    vectors = model(torch.rand(3, shape.band_count, shape.time_columns), torch.zeros(3))

    assert vectors.shape == (3, EMBEDDING_SIZE)
    torch.testing.assert_close(vectors.norm(dim=1), torch.ones(3))


def test_a_stored_descriptor_describes_a_waveform_the_way_it_did_before_storing(tmp_path: Path) -> None:
    shape = _shape()
    model = GridDescriptor(shape).eval()
    path = descriptor_path(tmp_path, name="tiny")
    canonicalizer = build_log_frequency_canonicalizer()
    waveform = np.sin(np.linspace(0.0, 800.0, 6000))[:, None]

    save_descriptor(path, model, _description(shape))
    loaded = load_descriptor(path, device=torch.device("cpu"))

    described = loaded.extract(waveform)
    assert described.shape == (EMBEDDING_SIZE,)
    assert described.dtype == np.float64
    np.testing.assert_allclose(np.linalg.norm(described), 1.0, rtol=1e-5)
    np.testing.assert_allclose(
        loaded.describe(canonicalizer.canonicalize(prepare_mono(waveform))), described, rtol=1e-5
    )
    assert loaded.size == EMBEDDING_SIZE


def test_a_missing_descriptor_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no descriptor is stored"):
        load_descriptor(descriptor_path(tmp_path, name="absent"), device=torch.device("cpu"))
