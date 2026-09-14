from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplecore.hashing import file_sha256
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from samplemorph.codecs.conditioned import (
    ConditionedCodec,
    ConditionedCodecDescription,
    codec_path,
    load_conditioned_codec,
    save_conditioned_codec,
)
from samplemorph.codecs.conditioned_model import ConditionedCodecModel, ConditionedCodecShape, ResidualLayout
from samplemorph.descriptors.grid_descriptor import DescriptorShape, GridDescriptor
from samplemorph.descriptors.learned import DescriptorDescription, descriptor_path, save_descriptor
from samplemorph.descriptors.pooling import DESCRIPTOR_BANDS_PER_SEMITONE, pooled_band_count
from samplemorph.geometry import log_frequency_geometry
from samplemorph.morphers import MorphWeights
from samplemorph.morphers.linear import LinearMorpher
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

DESCRIPTOR_SIZE = 16
RESIDUAL_SIZE = 8
DESCRIPTOR_NAME = "tiny-descriptor"


def _descriptor_shape() -> DescriptorShape:
    geometry = log_frequency_geometry()
    return DescriptorShape(
        band_count=pooled_band_count(geometry, bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE),
        time_columns=geometry.time_columns,
        width=4,
        stage_count=2,
        embedding_size=DESCRIPTOR_SIZE,
    )


def _codec_shape(layout: ResidualLayout = ResidualLayout.VECTOR) -> ConditionedCodecShape:
    geometry = log_frequency_geometry()
    return ConditionedCodecShape(
        band_count=geometry.grid_shape[0],
        time_columns=geometry.time_columns,
        descriptor_size=DESCRIPTOR_SIZE,
        residual_size=RESIDUAL_SIZE,
        width=4,
        layout=layout,
    )


def _store_descriptor(library_root: Path) -> None:
    torch.manual_seed(0)
    description = DescriptorDescription(
        canonicalizer="log_frequency",
        geometry=log_frequency_geometry(),
        bands_per_semitone=DESCRIPTOR_BANDS_PER_SEMITONE,
        shape=_descriptor_shape(),
        teacher_experiment_id=4,
        epochs=1,
        trained_sample_count=8,
        best_validation_loss=0.5,
    )
    save_descriptor(
        descriptor_path(library_root, name=DESCRIPTOR_NAME), GridDescriptor(_descriptor_shape()), description
    )


def _store_codec(library_root: Path, layout: ResidualLayout = ResidualLayout.VECTOR) -> Path:
    torch.manual_seed(1)
    shape = _codec_shape(layout)
    description = ConditionedCodecDescription(
        canonicalizer="log_frequency",
        geometry=log_frequency_geometry(),
        shape=shape,
        descriptor=DESCRIPTOR_NAME,
        descriptor_sha256=file_sha256(descriptor_path(library_root, name=DESCRIPTOR_NAME)),
        epochs=1,
        trained_sample_count=8,
        random_seed=0,
        best_validation_loss=0.5,
    )
    path = codec_path(library_root, name="tiny-codec")
    save_conditioned_codec(path, ConditionedCodecModel(shape), description)
    return path


def test_the_network_rebuilds_a_grid_of_the_shape_it_was_given() -> None:
    shape = _codec_shape()
    model = ConditionedCodecModel(shape).eval()
    grid = torch.rand(2, shape.band_count, shape.time_columns)
    descriptor = torch.nn.functional.normalize(torch.randn(2, DESCRIPTOR_SIZE), dim=-1)

    rebuilt, mean, log_variance = model(grid, descriptor)

    assert rebuilt.shape == grid.shape
    assert mean.shape == log_variance.shape == (2, RESIDUAL_SIZE)
    assert float(rebuilt.min()) >= 0.0 and float(rebuilt.max()) <= 1.0


def test_the_map_layout_holds_a_residual_at_every_bottleneck_cell() -> None:
    shape = _codec_shape(ResidualLayout.MAP)
    model = ConditionedCodecModel(shape).eval()
    grid = torch.rand(2, shape.band_count, shape.time_columns)
    descriptor = torch.nn.functional.normalize(torch.randn(2, DESCRIPTOR_SIZE), dim=-1)

    rebuilt, mean, log_variance = model(grid, descriptor)

    _channels, bands, columns = shape.bottleneck_shape
    assert mean.shape == log_variance.shape == (2, RESIDUAL_SIZE, bands, columns)
    assert shape.residual_shape == (RESIDUAL_SIZE, bands, columns)
    assert shape.residual_length == RESIDUAL_SIZE * bands * columns
    assert rebuilt.shape == grid.shape


def test_a_description_without_a_layout_reads_as_a_vector_residual() -> None:
    stored = _codec_shape().model_dump_json(exclude={"layout"})

    shape = ConditionedCodecShape.model_validate_json(stored)

    assert shape.layout is ResidualLayout.VECTOR
    assert shape.residual_shape == (RESIDUAL_SIZE,)
    assert shape.residual_length == RESIDUAL_SIZE


def test_training_draws_the_residual_and_evaluation_reads_its_mean() -> None:
    shape = _codec_shape()
    model = ConditionedCodecModel(shape)
    grid = torch.rand(1, shape.band_count, shape.time_columns)
    descriptor = torch.nn.functional.normalize(torch.randn(1, DESCRIPTOR_SIZE), dim=-1)

    model.eval()
    once, _, _ = model(grid, descriptor)
    twice, _, _ = model(grid, descriptor)
    torch.testing.assert_close(once, twice)
    model.train()
    drawn, _, _ = model(grid, descriptor)
    drawn_again, _, _ = model(grid, descriptor)
    assert not torch.equal(drawn, drawn_again)


def test_a_stored_codec_encodes_and_decodes_an_image_beside_its_descriptor(tmp_path: Path) -> None:
    _store_descriptor(tmp_path)
    path = _store_codec(tmp_path)
    canonicalizer = build_log_frequency_canonicalizer()
    image = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))

    codec = load_conditioned_codec(path, library_root=tmp_path, device=torch.device("cpu"))
    latent = codec.encode(image)
    decoded = codec.decode(latent)

    assert isinstance(codec, ConditionedCodec)
    assert codec.latent_size == latent.latent_size == DESCRIPTOR_SIZE + RESIDUAL_SIZE
    np.testing.assert_allclose(np.linalg.norm(latent.values[:DESCRIPTOR_SIZE]), 1.0, rtol=1e-5)
    assert decoded.grid.shape == image.grid.shape
    assert decoded.conditioners == image.conditioners
    assert 0.0 <= decoded.grid.min() and decoded.grid.max() <= 1.0


def test_a_map_codec_carries_its_residual_flattened_in_the_latent(tmp_path: Path) -> None:
    _store_descriptor(tmp_path)
    path = _store_codec(tmp_path, ResidualLayout.MAP)
    canonicalizer = build_log_frequency_canonicalizer()
    image = canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)))

    codec = load_conditioned_codec(path, library_root=tmp_path, device=torch.device("cpu"))
    latent = codec.encode(image)
    decoded = codec.decode(latent)

    assert codec.latent_size == latent.latent_size == DESCRIPTOR_SIZE + codec.model.shape.residual_length
    assert codec.model.shape.residual_length > RESIDUAL_SIZE
    assert decoded.grid.shape == image.grid.shape
    assert np.isfinite(decoded.grid).all()


@pytest.mark.parametrize("layout", tuple(ResidualLayout))
def test_a_morph_between_two_latents_decodes_to_a_grid(tmp_path: Path, layout: ResidualLayout) -> None:
    _store_descriptor(tmp_path)
    codec = load_conditioned_codec(_store_codec(tmp_path, layout), library_root=tmp_path, device=torch.device("cpu"))
    canonicalizer = build_log_frequency_canonicalizer()
    first = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=220.0))))
    second = codec.encode(canonicalizer.canonicalize(prepare_mono(harmonic_tone(TEST_FRAME_COUNT, frequency=330.0))))

    halfway = codec.decode(LinearMorpher().morph(first, second, weights=MorphWeights.uniform(0.5)))

    assert halfway.grid.shape == canonicalizer.geometry.grid_shape
    assert np.isfinite(halfway.grid).all()


def test_a_missing_codec_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no conditioned codec"):
        load_conditioned_codec(codec_path(tmp_path, name="absent"), library_root=tmp_path, device=torch.device("cpu"))


def test_a_codec_whose_descriptor_changed_since_it_was_trained_is_refused(tmp_path: Path) -> None:
    """A codec decodes from what its own descriptor says, so another file under that name is another codec's input."""
    _store_descriptor(tmp_path)
    path = _store_codec(tmp_path)
    torch.manual_seed(7)
    retrained = torch.load(descriptor_path(tmp_path, name=DESCRIPTOR_NAME), weights_only=True)
    save_descriptor(
        descriptor_path(tmp_path, name=DESCRIPTOR_NAME),
        GridDescriptor(_descriptor_shape()),
        DescriptorDescription.model_validate_json(str(retrained["description"])),
    )

    with pytest.raises(ValueError, match="another tiny-descriptor descriptor"):
        load_conditioned_codec(path, library_root=tmp_path, device=torch.device("cpu"))
