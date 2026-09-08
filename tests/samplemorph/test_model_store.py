from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import constant_q_geometry, mel_geometry
from samplemorph.model_store import (
    IDENTITY_CODEC_NAME,
    MODELS_DIRECTORY_NAME,
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    describe_json,
    load_model,
    model_path,
    save_model,
)
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.principal_components import PrincipalComponentTrainer
from tests.samplemorph.conftest import harmonic_tone

LATENT_SIZE = 4
IMAGE_COUNT = 12
FIT_FRAME_COUNT = 4096
MODEL_NAME = "under-test"


def _images() -> list:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    return [
        canonicalizer.canonicalize(harmonic_tone(FIT_FRAME_COUNT, frequency=110.0 * (1.0 + index / 3.0)))
        for index in range(IMAGE_COUNT)
    ]


def _description(codec_name: str, *, latent_size: int) -> MorphModelDescription:
    return MorphModelDescription(
        codec=codec_name,
        canonicalizer="mel",
        geometry=mel_geometry(),
        latent_size=latent_size,
        fitted_sample_count=IMAGE_COUNT,
        random_seed=0,
        explained_variance=0.5,
    )


def test_a_model_path_sits_under_the_library_root(tmp_path: Path) -> None:
    """Fitted models live beside the audio, keeping the repository to machinery alone."""
    path = model_path(tmp_path, name=MODEL_NAME)

    assert path.parent == tmp_path / MODELS_DIRECTORY_NAME
    assert path.name == f"{MODEL_NAME}.npz"


def test_a_projection_survives_a_write_and_a_read(tmp_path: Path) -> None:
    images = _images()
    codec = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(images)
    path = model_path(tmp_path, name=MODEL_NAME)

    save_model(
        path, MorphModel(description=_description(PRINCIPAL_COMPONENT_CODEC_NAME, latent_size=LATENT_SIZE), codec=codec)
    )
    restored = load_model(path)

    assert np.allclose(restored.codec.encode(images[0]).values, codec.encode(images[0]).values)
    assert restored.description.latent_size == LATENT_SIZE


def test_a_restored_model_carries_the_axis_it_was_fitted_on(tmp_path: Path) -> None:
    """A later change to the shared defaults leaves an existing file honest about its own axis."""
    codec = IdentityCodec(mel_geometry())
    path = model_path(tmp_path, name=MODEL_NAME)
    save_model(
        path, MorphModel(description=_description(IDENTITY_CODEC_NAME, latent_size=codec.latent_size), codec=codec)
    )

    restored = load_model(path)

    assert restored.description.geometry == mel_geometry()
    assert restored.description.geometry != constant_q_geometry()


def test_an_identity_codec_survives_a_write_and_a_read(tmp_path: Path) -> None:
    codec = IdentityCodec(mel_geometry())
    image = _images()[0]
    path = model_path(tmp_path, name=MODEL_NAME)
    save_model(
        path, MorphModel(description=_description(IDENTITY_CODEC_NAME, latent_size=codec.latent_size), codec=codec)
    )

    restored = load_model(path)

    assert np.array_equal(restored.codec.decode(restored.codec.encode(image)).grid, image.grid)


def test_reading_a_model_naming_an_unknown_codec_says_so(tmp_path: Path) -> None:
    path = model_path(tmp_path, name=MODEL_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.savez(handle, description=np.array(_description("stargazer", latent_size=1).model_dump_json()))

    with pytest.raises(ValueError, match="no reader is registered"):
        load_model(path)


def test_a_description_renders_as_readable_json() -> None:
    rendered = describe_json(_description(PRINCIPAL_COMPONENT_CODEC_NAME, latent_size=LATENT_SIZE))

    assert '"codec": "principal_components"' in rendered
    assert '"canonicalizer": "mel"' in rendered
