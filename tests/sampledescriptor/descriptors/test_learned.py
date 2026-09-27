from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from sampledescriptor.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from sampledescriptor.descriptors.grid_descriptor import GridDescriptor
from sampledescriptor.descriptors.learned import DescriptorDescription, load_descriptor, save_descriptor
from sampledescriptor.descriptors.shape import DescriptorShape
from sampledescriptor.model_paths import descriptor_path
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import log_frequency_geometry
from tests.sampledescriptor.conftest import TINY_EMBEDDING_SIZE


def test_the_network_answers_with_one_unit_vector_per_grid(descriptor_shape: DescriptorShape) -> None:
    shape = descriptor_shape
    model = GridDescriptor(shape)

    vectors = model(torch.rand(3, shape.band_count, shape.time_columns), torch.zeros(3))

    assert vectors.shape == (3, TINY_EMBEDDING_SIZE)
    torch.testing.assert_close(vectors.norm(dim=1), torch.ones(3))


def test_a_stored_descriptor_describes_a_waveform_the_way_it_did_before_storing(
    tmp_path: Path, descriptor_description: DescriptorDescription
) -> None:
    shape = descriptor_description.shape
    model = GridDescriptor(shape).eval()
    path = descriptor_path(tmp_path, name="tiny")
    canonicalizer = build_log_frequency_canonicalizer()
    waveform = np.sin(np.linspace(0.0, 800.0, 6000))[:, None]

    save_descriptor(path, model, descriptor_description)
    loaded = load_descriptor(path, device=torch.device("cpu"))

    described = loaded.extract(waveform)
    assert described.shape == (TINY_EMBEDDING_SIZE,)
    assert described.dtype == np.float64
    np.testing.assert_allclose(np.linalg.norm(described), 1.0, rtol=1e-5)
    np.testing.assert_allclose(
        loaded.describe(canonicalizer.canonicalize(prepare_mono(waveform))), described, rtol=1e-5
    )
    assert loaded.size == TINY_EMBEDDING_SIZE


def test_a_missing_descriptor_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no descriptor is stored"):
        load_descriptor(descriptor_path(tmp_path, name="absent"), device=torch.device("cpu"))
