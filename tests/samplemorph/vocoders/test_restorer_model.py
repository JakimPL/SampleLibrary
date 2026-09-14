from __future__ import annotations

import numpy as np
import pytest
import torch

from samplemorph.vocoders.levels import peak_level
from samplemorph.vocoders.restorer_model import Restorer, compress, expand
from samplemorph.vocoders.restorer_shape import RestorerShape

BIN_COUNT = 33
DYNAMIC_RANGE_DB = 100.0
FRAME_COUNT = 16
BATCH_SIZE = 2
SMALL_SHAPE = RestorerShape(channels=16, kernel_size=3, dilations=(1, 2))


def _decibels(generator: torch.Generator) -> torch.Tensor:
    return -torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT, generator=generator)


def test_an_untrained_restorer_hands_the_reading_through_unchanged() -> None:
    """The output layer starts at zero, so training begins at the least-squares baseline."""
    torch.manual_seed(0)
    model = Restorer(SMALL_SHAPE).eval()
    decibels = _decibels(torch.Generator().manual_seed(1))

    with torch.no_grad():
        restored = model(decibels)

    assert restored.shape == decibels.shape
    assert torch.equal(restored, decibels)


def test_the_restorer_serves_any_transform_length() -> None:
    torch.manual_seed(0)
    model = Restorer(SMALL_SHAPE).eval()
    wider = -torch.rand(BATCH_SIZE, 2 * BIN_COUNT + 1, FRAME_COUNT + 5)

    with torch.no_grad():
        restored = model(wider)

    assert restored.shape == wider.shape


def test_a_step_of_training_moves_the_restorer_off_the_baseline() -> None:
    torch.manual_seed(0)
    model = Restorer(SMALL_SHAPE)
    decibels = _decibels(torch.Generator().manual_seed(1))
    target = decibels + 0.1
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)

    loss = torch.nn.functional.l1_loss(model(decibels), target)
    loss.backward()
    optimizer.step()
    with torch.no_grad():
        moved = model(decibels)

    assert loss.item() == pytest.approx(0.1)
    assert not torch.equal(moved, decibels)
    assert torch.isfinite(moved).all()


def test_the_peak_reads_as_zero_and_the_dynamic_range_floor_as_minus_one() -> None:
    magnitude = np.array([[1.0, 10.0 ** (-DYNAMIC_RANGE_DB / 20.0), 0.0]])

    decibels = compress(magnitude, peak=peak_level(magnitude), dynamic_range_db=DYNAMIC_RANGE_DB)

    assert decibels.dtype == np.float32
    np.testing.assert_allclose(decibels, [[0.0, -1.0, -1.0]], atol=1e-6)


def test_a_quiet_magnitude_and_a_loud_one_compress_to_the_same_picture() -> None:
    magnitude = np.random.default_rng(0).random((BIN_COUNT, FRAME_COUNT)) + 0.01

    quiet = compress(magnitude * 1e-4, peak=peak_level(magnitude * 1e-4), dynamic_range_db=DYNAMIC_RANGE_DB)
    loud = compress(magnitude * 1e2, peak=peak_level(magnitude * 1e2), dynamic_range_db=DYNAMIC_RANGE_DB)

    np.testing.assert_allclose(quiet, loud, atol=1e-5)


def test_expanding_a_compressed_magnitude_gives_it_back_above_the_floor() -> None:
    magnitude = np.random.default_rng(0).random((BIN_COUNT, FRAME_COUNT)) + 0.01
    peak = peak_level(magnitude)

    recovered = expand(
        compress(magnitude, peak=peak, dynamic_range_db=DYNAMIC_RANGE_DB), peak=peak, dynamic_range_db=DYNAMIC_RANGE_DB
    )

    np.testing.assert_allclose(recovered, magnitude, rtol=1e-5)


def test_silence_is_read_against_the_floor_and_comes_back_silent() -> None:
    silence = np.zeros((BIN_COUNT, FRAME_COUNT))
    peak = peak_level(silence)

    decibels = compress(silence, peak=peak, dynamic_range_db=DYNAMIC_RANGE_DB)

    assert peak > 0.0
    np.testing.assert_allclose(decibels, -np.ones_like(decibels), atol=1e-6)
    assert expand(decibels, peak=peak, dynamic_range_db=DYNAMIC_RANGE_DB).max() < 1e-9
