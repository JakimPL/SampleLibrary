from __future__ import annotations

import numpy as np
import pytest

from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import mel_geometry
from samplemorph.images import Conditioners, SoundImage
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.principal_components import PrincipalComponentTrainer
from tests.samplemorph.conftest import harmonic_tone, noise_burst

LATENT_SIZE = 6
IMAGE_COUNT = 24
FIT_FRAME_COUNT = 4096


def _images(count: int) -> list[SoundImage]:
    """A body of images spanning tone and noise, enough to fit a small projection over."""
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    built = []
    for index in range(count):
        frequency = 110.0 * (1.0 + index / 4.0)
        waveform = (
            harmonic_tone(FIT_FRAME_COUNT, frequency=frequency)
            if index % 2 == 0
            else noise_burst(FIT_FRAME_COUNT, seed=index)
        )
        built.append(canonicalizer.canonicalize(waveform))
    return built


def test_the_identity_codec_returns_exactly_what_it_was_given() -> None:
    """Losing nothing is what makes this codec the floor every other one is read against."""
    geometry = mel_geometry()
    codec = IdentityCodec(geometry)
    image = _images(1)[0]

    decoded = codec.decode(codec.encode(image))

    assert np.array_equal(decoded.grid, image.grid)
    assert decoded.conditioners == image.conditioners


def test_the_identity_codec_reports_a_latent_the_size_of_the_grid() -> None:
    geometry = mel_geometry()

    assert IdentityCodec(geometry).latent_size == geometry.band_count * geometry.time_columns


def test_a_projection_keeps_the_conditioners_untouched() -> None:
    """The conditioners describe the frame the grid was normalized into, so a codec passes them on."""
    images = _images(IMAGE_COUNT)
    codec = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(images)

    decoded = codec.decode(codec.encode(images[0]))

    assert decoded.conditioners == images[0].conditioners


def test_a_projection_reports_the_latent_size_it_was_asked_for() -> None:
    codec = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(_images(IMAGE_COUNT))

    assert codec.latent_size == LATENT_SIZE
    assert codec.encode(_images(1)[0]).latent_size == LATENT_SIZE


def test_a_projection_reconstructs_a_fitted_image_more_closely_than_the_body_average() -> None:
    """A projection is worth having when it beats simply returning the mean of what it was fitted on."""
    images = _images(IMAGE_COUNT)
    codec = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(images)

    decoded = codec.decode(codec.encode(images[0]))
    average = np.mean([image.grid for image in images], axis=0)

    projection_error = float(np.sqrt(np.mean((decoded.grid - images[0].grid) ** 2)))
    average_error = float(np.sqrt(np.mean((average - images[0].grid) ** 2)))
    assert projection_error < average_error


def test_a_projection_holds_more_of_the_variance_as_it_keeps_more_components() -> None:
    images = _images(IMAGE_COUNT)

    narrow = PrincipalComponentTrainer(mel_geometry(), latent_size=2, random_seed=0).fit(images)
    wide = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(images)

    assert wide.explained_variance > narrow.explained_variance
    assert wide.explained_variance_ratio.shape == (LATENT_SIZE,)


def test_a_decoded_grid_stays_within_the_range_an_image_occupies() -> None:
    """Clipping is what keeps a point between two grids on the manifold a real image describes."""
    images = _images(IMAGE_COUNT)
    codec = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(images)
    latent = codec.encode(images[0])
    exaggerated = type(latent)(values=latent.values * 20.0, conditioners=latent.conditioners, geometry=latent.geometry)

    decoded = codec.decode(exaggerated)

    assert decoded.grid.min() >= 0.0
    assert decoded.grid.max() <= 1.0


def test_fitting_more_components_than_images_says_so() -> None:
    with pytest.raises(ValueError, match="at least that many images"):
        PrincipalComponentTrainer(mel_geometry(), latent_size=IMAGE_COUNT + 1, random_seed=0).fit(_images(IMAGE_COUNT))


def test_a_latent_must_be_one_dimensional() -> None:
    geometry = mel_geometry()
    conditioners = Conditioners(translation_semitones=0.0, log_duration=-2.0, log_gain=-1.0)
    latent_type = type(IdentityCodec(geometry).encode(_images(1)[0]))

    with pytest.raises(ValueError, match="1-D"):
        latent_type(values=np.zeros((2, 2)), conditioners=conditioners, geometry=geometry)
