from __future__ import annotations

import numpy as np
import pytest
import torch

from samplemorph.training.phase_losses import (
    AnalysisWindow,
    LossWeights,
    multi_resolution_spectral_error,
    phase_gradient_error,
    phase_loss,
    rotate_back,
    to_waveform,
)
from samplemorph.vocoders.phase_model import PhaseModel, PhaseModelShape, compress, nominal_turning

BIN_COUNT = 65
FRAME_COUNT = 24
BATCH_SIZE = 2
SMALL_SHAPE = PhaseModelShape(bin_count=BIN_COUNT, channels=32, kernel_size=3, dilations=(1, 2))


def _unit_phase(generator: torch.Generator) -> torch.Tensor:
    angle = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT, generator=generator) * 2.0 * np.pi
    return torch.stack((torch.cos(angle), torch.sin(angle)), dim=1)


def test_the_model_returns_one_point_on_the_unit_circle_per_bin_and_frame() -> None:
    """An angle wraps at its own boundary, so the model states a point rather than a number."""
    model = PhaseModel(SMALL_SHAPE)
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT)

    phase = model(magnitude)

    assert phase.shape == (BATCH_SIZE, 2, BIN_COUNT, FRAME_COUNT)
    assert torch.allclose(phase.norm(dim=1), torch.ones(BATCH_SIZE, BIN_COUNT, FRAME_COUNT), atol=1e-5)


def test_a_quiet_sample_and_a_loud_one_are_read_the_same_way() -> None:
    """A sample's level says nothing about its phase, so the input is read against its own peak.

    The reading is compared directly; a network's own weights magnify whatever difference reaches
    them, so a figure taken from its output would describe the weights rather than the reading.
    """
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT) + 0.01

    assert torch.allclose(compress(magnitude * 1e-4), compress(magnitude * 1e2), atol=1e-5)


def test_the_model_answers_a_quiet_sample_and_a_loud_one_alike() -> None:
    torch.manual_seed(0)
    model = PhaseModel(SMALL_SHAPE).eval()
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT) + 0.01

    with torch.no_grad():
        quiet = model(magnitude * 1e-4)
        loud = model(magnitude * 1e2)

    assert torch.allclose(quiet, loud, atol=1e-3)


def test_compression_puts_a_peak_at_the_top_of_its_range() -> None:
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT) + 0.01

    compressed = compress(magnitude)

    assert float(compressed.max()) == pytest.approx(1.0, abs=1e-5)
    assert float(compressed.min()) >= -1.0


def test_a_phase_against_itself_leaves_no_rotation() -> None:
    phase = _unit_phase(torch.Generator().manual_seed(0))

    rotated = rotate_back(phase, phase)

    assert torch.allclose(rotated[:, 0], torch.ones_like(rotated[:, 0]), atol=1e-5)
    assert torch.allclose(rotated[:, 1], torch.zeros_like(rotated[:, 1]), atol=1e-5)


def test_the_gradient_error_is_zero_for_the_phase_it_was_given() -> None:
    phase = _unit_phase(torch.Generator().manual_seed(1))
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT)

    assert float(phase_gradient_error(phase, phase, magnitude)) == pytest.approx(0.0, abs=1e-6)


def test_the_gradient_error_ignores_one_angle_shared_by_the_whole_picture() -> None:
    """The property this loss exists for.

    A magnitude fixes its signal's phase only up to a single shared angle -- delaying a waveform
    within one sample turns every phase and moves no magnitude -- so a loss that read absolute
    angles would punish a model for something the magnitude never determined.
    """
    phase = _unit_phase(torch.Generator().manual_seed(2))
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT)
    turn = torch.tensor(0.7)
    rotated = torch.stack(
        (
            phase[:, 0] * torch.cos(turn) - phase[:, 1] * torch.sin(turn),
            phase[:, 0] * torch.sin(turn) + phase[:, 1] * torch.cos(turn),
        ),
        dim=1,
    )

    assert float(phase_gradient_error(rotated, phase, magnitude)) == pytest.approx(0.0, abs=1e-5)


def test_the_gradient_error_reports_a_phase_that_advances_differently() -> None:
    generator = torch.Generator().manual_seed(3)
    phase = _unit_phase(generator)
    other = _unit_phase(generator)
    magnitude = torch.ones(BATCH_SIZE, BIN_COUNT, FRAME_COUNT)

    assert float(phase_gradient_error(other, phase, magnitude)) > 1.0


def test_the_spectral_error_is_zero_for_a_waveform_against_itself() -> None:
    waveform = torch.randn(BATCH_SIZE, 8192)

    assert float(multi_resolution_spectral_error(waveform, waveform)) == pytest.approx(0.0, abs=1e-6)


def test_the_loss_reports_the_terms_it_is_made_of() -> None:
    generator = torch.Generator().manual_seed(4)
    magnitude = torch.rand(BATCH_SIZE, 129, FRAME_COUNT)
    angle = torch.rand(BATCH_SIZE, 129, FRAME_COUNT, generator=generator) * 2.0 * np.pi
    target = torch.stack((torch.cos(angle), torch.sin(angle)), dim=1)
    predicted = torch.stack((torch.cos(angle + 0.3), torch.sin(angle + 0.3)), dim=1)

    parts = phase_loss(
        predicted,
        target,
        magnitude,
        window=AnalysisWindow(fft_length=256, hop_length=64, taper=torch.hann_window(256)),
        weights=LossWeights(),
    )

    assert float(parts.total) > 0.0
    assert float(parts.gradient) >= 0.0
    assert float(parts.spectral) >= 0.0


def test_a_magnitude_and_a_phase_make_a_waveform_of_the_frames_they_span() -> None:
    """`BIN_COUNT` bins are what a 128-point window produces, so the two agree by construction."""
    magnitude = torch.rand(BATCH_SIZE, BIN_COUNT, FRAME_COUNT)
    phase = _unit_phase(torch.Generator().manual_seed(5))

    waveform = to_waveform(
        magnitude, phase, window=AnalysisWindow(fft_length=128, hop_length=32, taper=torch.hann_window(128))
    )

    assert waveform.shape[0] == BATCH_SIZE
    assert torch.isfinite(waveform).all()


def test_the_turning_a_crop_is_told_about_is_the_turning_its_own_phase_does() -> None:
    """The correction this input exists for.

    Two crops of one sample taken at different moments carry phases that differ by a delay. Reading
    the turning from each crop's own start puts that delay back, so the model is asked for the phase
    its example really has rather than for one it has no way to know.
    """
    magnitude = torch.rand(1, BIN_COUNT, FRAME_COUNT)

    from_start = nominal_turning(magnitude, frames_per_turn=8, frame_offset=torch.tensor([0.0]))
    from_later = nominal_turning(magnitude, frames_per_turn=8, frame_offset=torch.tensor([3.0]))
    longer = nominal_turning(
        torch.rand(1, BIN_COUNT, FRAME_COUNT + 3), frames_per_turn=8, frame_offset=torch.tensor([0.0])
    )

    assert torch.allclose(from_later, longer[:, :, 3:], atol=1e-5)
    assert not torch.allclose(from_later, from_start, atol=1e-3)


def test_the_turning_stays_on_the_unit_circle() -> None:
    magnitude = torch.rand(2, BIN_COUNT, FRAME_COUNT)

    turning = nominal_turning(magnitude, frames_per_turn=8, frame_offset=torch.tensor([0.0, 5.0]))

    assert turning.shape == (2, 2 * BIN_COUNT, FRAME_COUNT)
    assert torch.allclose(
        turning[:, :BIN_COUNT] ** 2 + turning[:, BIN_COUNT:] ** 2,
        torch.ones(2, BIN_COUNT, FRAME_COUNT),
        atol=1e-5,
    )
