from __future__ import annotations

import numpy as np
import pytest

from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import mel_geometry
from samplemorph.images import SoundImage
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.principal_components import PrincipalComponentTrainer, stack_grids
from tests.samplemorph.conftest import harmonic_tone, noise_burst

IMAGE_COUNT = 12
LATENT_SIZE = 4
FRAME_COUNT = 4096


def _images() -> list[SoundImage]:
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    return [
        canonicalizer.canonicalize(
            prepare_mono(
                harmonic_tone(FRAME_COUNT, frequency=110.0 * (1 + index))
                if index % 2 == 0
                else noise_burst(FRAME_COUNT, seed=index)
            )
        )
        for index in range(IMAGE_COUNT)
    ]


def test_grids_are_laid_out_one_per_row_in_the_order_they_arrive() -> None:
    images = _images()

    matrix = stack_grids(iter(images), count=len(images), geometry=mel_geometry())

    assert matrix.dtype == np.float32
    np.testing.assert_allclose(matrix[3], images[3].grid.reshape(-1), atol=1e-6)


@pytest.mark.parametrize("count", [IMAGE_COUNT - 1, IMAGE_COUNT + 1], ids=("fewer rows", "more rows"))
def test_a_matrix_laid_out_for_another_count_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="grids"):
        stack_grids(iter(_images()), count=count, geometry=mel_geometry())


def test_a_single_precision_fit_finds_what_a_double_precision_one_does() -> None:
    images = _images()
    single = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(
        stack_grids(images, count=IMAGE_COUNT, geometry=mel_geometry())
    )
    double = PrincipalComponentTrainer(mel_geometry(), latent_size=LATENT_SIZE, random_seed=0).fit(
        np.stack([image.grid.reshape(-1) for image in images])  # type: ignore[arg-type]
    )

    assert single.components.dtype == np.float32
    assert single.explained_variance == pytest.approx(double.explained_variance, abs=1e-4)
