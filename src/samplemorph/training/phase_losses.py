from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor

MULTI_RESOLUTION_WINDOWS: Final[tuple[int, ...]] = (512, 1024, 2048)
OVERLAP_DIVISOR: Final[int] = 4
LOG_FLOOR: Final[float] = 1e-5
DEFAULT_GRADIENT_WEIGHT: Final[float] = 1.0
DEFAULT_SPECTRAL_WEIGHT: Final[float] = 1.0


@dataclass(frozen=True)
class LossWeights:
    """How much each term counts toward what the model is asked to do.

    The gradient term teaches how phase advances from frame to frame and from bin to bin, and the
    spectral term holds the audio that advance produces against the audio it should have been.
    """

    gradient: float = DEFAULT_GRADIENT_WEIGHT
    spectral: float = DEFAULT_SPECTRAL_WEIGHT


@dataclass(frozen=True)
class AnalysisWindow:
    """The window a loss listens through: how long it is, how far it steps, and its taper.

    The three travel together because they only mean anything together -- a taper of one length
    describes a different analysis when read at a different hop.
    """

    fft_length: int
    hop_length: int
    taper: Tensor


@dataclass(frozen=True)
class LossParts:
    """What one training step's loss was made of, so a run says which term is moving."""

    total: Tensor
    gradient: Tensor
    spectral: Tensor


def rotate_back(first: Tensor, second: Tensor) -> Tensor:
    """How far one unit phase sits from another, as a unit phase of its own.

    Multiplying by the conjugate turns a pair of angles into the angle between them, which is what
    makes a difference of phases readable without ever unwrapping one.
    """
    cosine = first[:, 0] * second[:, 0] + first[:, 1] * second[:, 1]
    sine = first[:, 1] * second[:, 0] - first[:, 0] * second[:, 1]
    return torch.stack((cosine, sine), dim=1)


def phase_gradient_error(predicted: Tensor, target: Tensor, magnitude: Tensor) -> Tensor:
    """How far the predicted phase advances from how the true phase advances.

    A magnitude fixes its signal's phase only up to one angle shared by the whole picture: delaying
    a waveform within a single sample turns every phase without moving any magnitude. Reading the
    advance from frame to frame and from bin to bin asks for what the magnitude does determine, and
    an advance right everywhere fixes the whole field but for that one inaudible constant.

    Each difference counts as much as the quieter of the two bins it spans, so the model spends its
    capacity where a listener would notice the phase being wrong.
    """
    weight_scale = magnitude.amax(dim=(1, 2), keepdim=True).clamp_min(LOG_FLOOR)
    scaled = magnitude / weight_scale
    total = predicted.new_zeros(())
    for shift in (_along_time, _along_frequency):
        predicted_step, target_step, weight = shift(predicted, target, scaled)
        error = (predicted_step - target_step).square().sum(dim=1)
        total = total + (error * weight).sum() / weight.sum().clamp_min(LOG_FLOOR)
    return total / 2.0


def _along_time(predicted: Tensor, target: Tensor, magnitude: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    return (
        rotate_back(predicted[:, :, :, 1:], predicted[:, :, :, :-1]),
        rotate_back(target[:, :, :, 1:], target[:, :, :, :-1]),
        torch.minimum(magnitude[:, :, 1:], magnitude[:, :, :-1]),
    )


def _along_frequency(predicted: Tensor, target: Tensor, magnitude: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    return (
        rotate_back(predicted[:, :, 1:, :], predicted[:, :, :-1, :]),
        rotate_back(target[:, :, 1:, :], target[:, :, :-1, :]),
        torch.minimum(magnitude[:, 1:, :], magnitude[:, :-1, :]),
    )


def to_waveform(magnitude: Tensor, phase: Tensor, *, window: AnalysisWindow) -> Tensor:
    """Make one magnitude and one angle audible, which is what the loss below listens to."""
    spectrum = torch.complex(magnitude * phase[:, 0], magnitude * phase[:, 1])
    # pylint: disable-next=not-callable
    waveform: Tensor = torch.istft(spectrum, n_fft=window.fft_length, hop_length=window.hop_length, window=window.taper)
    return waveform


def multi_resolution_spectral_error(predicted: Tensor, target: Tensor) -> Tensor:
    """Compare two waveforms' magnitudes through several window lengths at once.

    Phase that no signal could carry shows up here rather than in the magnitude it was read from:
    making it audible and reading the result back reveals the disagreement, at whichever window
    length the disagreement lives.
    """
    total = predicted.new_zeros(())
    for fft_length in MULTI_RESOLUTION_WINDOWS:
        window = torch.hann_window(fft_length, device=predicted.device)
        # pylint: disable-next=not-callable
        predicted_magnitude = torch.stft(
            predicted, n_fft=fft_length, hop_length=fft_length // OVERLAP_DIVISOR, window=window, return_complex=True
        ).abs()
        # pylint: disable-next=not-callable
        target_magnitude = torch.stft(
            target, n_fft=fft_length, hop_length=fft_length // OVERLAP_DIVISOR, window=window, return_complex=True
        ).abs()
        total = total + torch.nn.functional.l1_loss(
            torch.log(predicted_magnitude.clamp_min(LOG_FLOOR)), torch.log(target_magnitude.clamp_min(LOG_FLOOR))
        )
    return total / len(MULTI_RESOLUTION_WINDOWS)


def phase_loss(
    predicted_phase: Tensor,
    target_phase: Tensor,
    magnitude: Tensor,
    *,
    window: AnalysisWindow,
    weights: LossWeights,
) -> LossParts:
    """What the model is trained on: how phase advances, and how the audio it makes reads back.

    The target waveform is this same magnitude carried by its own true phase, which is the
    reconstruction listening has already accepted. Holding the model against that asks it for the
    phase the grid's magnitude deserves rather than asking it to restore what the grid discarded.
    """
    predicted_waveform = to_waveform(magnitude, predicted_phase, window=window)
    target_waveform = to_waveform(magnitude, target_phase, window=window)
    gradient = phase_gradient_error(predicted_phase, target_phase, magnitude)
    spectral = multi_resolution_spectral_error(predicted_waveform, target_waveform)
    return LossParts(
        total=weights.gradient * gradient + weights.spectral * spectral, gradient=gradient, spectral=spectral
    )
