from __future__ import annotations

import torch

from samplemorph.training.features.losses import (
    MAXIMUM_SHARE,
    critic_loss,
    drawn_shares,
    interpolated,
    realistic_mix,
    spread_shares,
)

CPU = torch.device("cpu")


def test_a_latent_mixed_at_share_one_is_itself_and_at_share_zero_its_neighbor() -> None:
    latents = torch.arange(12, dtype=torch.float32).view(4, 3)

    assert torch.equal(interpolated(latents, torch.ones(4)), latents)
    assert torch.equal(interpolated(latents, torch.zeros(4)), torch.roll(latents, shifts=1, dims=0))


def test_every_share_lies_between_an_end_and_the_midpoint() -> None:
    torch.manual_seed(0)
    drawn = drawn_shares(1000, device=CPU)
    spread = spread_shares(5, device=CPU)

    assert float(drawn.min()) >= 0.0
    assert float(drawn.max()) <= MAXIMUM_SHARE
    assert torch.allclose(spread, torch.tensor([0.0, 0.125, 0.25, 0.375, 0.5]))


def test_a_critic_that_reads_every_share_and_calls_every_sound_a_sound_loses_nothing() -> None:
    shares = torch.tensor([0.1, 0.3, 0.5])

    assert float(critic_loss(shares, shares, realistic_scores=torch.zeros(3))) == 0.0
    assert float(critic_loss(torch.zeros(3), shares, realistic_scores=torch.zeros(3))) > 0.0
    assert float(critic_loss(shares, shares, realistic_scores=torch.ones(3))) > 0.0


def test_a_realistic_mix_holds_the_sound_s_share_of_itself() -> None:
    grids, reconstructions = torch.ones(2, 3), torch.zeros(2, 3)

    assert torch.allclose(realistic_mix(grids, reconstructions, mix=0.2), torch.full((2, 3), 0.2))
