from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplemorph.features.autoencoder import FeatureAutoencoder
from samplemorph.features.critic import InterpolationCritic
from samplemorph.features.shape import FeatureShape
from samplemorph.features.store import FeatureDescription, load_features, save_features
from samplemorph.geometry import log_frequency_geometry

SHAPE = FeatureShape(band_count=16, time_columns=8, latent_size=4, width=4, stage_count=2)
CPU = torch.device("cpu")


def _description() -> FeatureDescription:
    return FeatureDescription(
        cache="tiny",
        canonicalizer="log_frequency",
        geometry=log_frequency_geometry(),
        bands_per_semitone=1,
        shape=SHAPE,
        critic_weight=0.5,
        critic_mix=0.2,
        random_seed=0,
        epochs=3,
        trained_sample_count=20,
        best_validation_loss=0.1,
        validation_hashes=(format(1, "064x"), format(2, "064x")),
    )


def test_a_stored_model_reads_and_scores_exactly_as_the_networks_it_was_written_from(tmp_path: Path) -> None:
    torch.manual_seed(0)
    autoencoder, critic = FeatureAutoencoder(SHAPE).eval(), InterpolationCritic(SHAPE).eval()
    path = tmp_path / "features.pt"
    grids = np.random.default_rng(0).random((5, SHAPE.band_count, SHAPE.time_columns), dtype=np.float32)

    save_features(path, autoencoder=autoencoder, critic=critic, description=_description())
    stored = load_features(path, device=CPU)

    with torch.no_grad():
        expected_latents = autoencoder.encoder(torch.from_numpy(grids)).numpy()
        expected_grids = autoencoder.decoder(torch.from_numpy(expected_latents)).numpy()
        expected_scores = critic(torch.from_numpy(grids)).numpy()
    assert stored.description == _description()
    assert np.array_equal(stored.encode(grids), expected_latents)
    assert np.array_equal(stored.decode(expected_latents), expected_grids)
    assert np.array_equal(stored.score(grids), expected_scores)
    assert stored.encode(grids).dtype == np.float32


def test_loading_a_model_nobody_stored_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_features(tmp_path / "absent.pt", device=CPU)
