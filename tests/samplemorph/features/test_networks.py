from __future__ import annotations

from dataclasses import dataclass

import pytest
import torch
from pydantic import ValidationError

from samplemorph.features.autoencoder import FeatureAutoencoder
from samplemorph.features.critic import InterpolationCritic
from samplemorph.features.shape import FeatureShape

BATCH = 3


@dataclass(frozen=True)
class ShapeCase:
    name: str
    shape: FeatureShape


SHAPE_CASES = (
    ShapeCase("the pooled cache's grid", FeatureShape(band_count=113, time_columns=64, latent_size=16, width=4)),
    ShapeCase("a grid every stage halves evenly", FeatureShape(band_count=16, time_columns=8, width=4, stage_count=2)),
    ShapeCase("a grid narrower than one deepest cell", FeatureShape(band_count=5, time_columns=3, width=4)),
)


@pytest.mark.parametrize("case", SHAPE_CASES, ids=[case.name for case in SHAPE_CASES])
def test_a_grid_is_read_into_a_latent_and_decoded_back_to_its_own_shape_within_the_cache_s_range(
    case: ShapeCase,
) -> None:
    torch.manual_seed(0)
    autoencoder = FeatureAutoencoder(case.shape)
    grids = torch.rand(BATCH, case.shape.band_count, case.shape.time_columns)

    with torch.no_grad():
        latents = autoencoder.encoder(grids)
        decoded = autoencoder.decoder(latents)

    assert latents.shape == (BATCH, case.shape.latent_size)
    assert decoded.shape == grids.shape
    assert float(decoded.min()) >= 0.0
    assert float(decoded.max()) <= 1.0


@pytest.mark.parametrize("case", SHAPE_CASES, ids=[case.name for case in SHAPE_CASES])
def test_the_critic_answers_one_number_per_grid(case: ShapeCase) -> None:
    critic = InterpolationCritic(case.shape)

    scores = critic(torch.rand(BATCH, case.shape.band_count, case.shape.time_columns))

    assert scores.shape == (BATCH,)


def test_the_encoder_reads_where_along_the_band_axis_a_feature_sits() -> None:
    """A flattened deepest map keeps position, so a feature moved along the bands reads as another latent."""
    torch.manual_seed(0)
    shape = FeatureShape(band_count=32, time_columns=8, latent_size=8, width=4, stage_count=2)
    encoder = FeatureAutoencoder(shape).encoder
    low = torch.zeros(1, 32, 8)
    low[:, 4:6] = 1.0
    high = torch.roll(low, shifts=16, dims=1)

    assert not torch.allclose(encoder(low), encoder(high), atol=1e-4)


def test_a_width_the_normalization_cannot_group_is_refused() -> None:
    with pytest.raises(ValidationError):
        FeatureShape(band_count=16, time_columns=8, width=6)
