from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor, nn

DEFAULT_CHANNELS: Final[int] = 512
DEFAULT_KERNEL_SIZE: Final[int] = 5
DEFAULT_DILATIONS: Final[tuple[int, ...]] = (1, 2, 4, 8, 1, 2, 4, 8)
DEFAULT_FRAMES_PER_TURN: Final[int] = 8
MAGNITUDE_FLOOR: Final[float] = 1e-7
DYNAMIC_RANGE_DB: Final[float] = 100.0


@dataclass(frozen=True)
class PhaseModelShape:
    """The grid a phase model reads and the capacity it spends on it.

    The bin count follows from the analysis window, so a checkpoint carries this and a vocoder
    rebuilds the same network rather than guessing at it. `frames_per_turn` says how many frames a
    bin one step above the lowest takes to come back round, which is the rate every bin's phase
    turns at before anything about the sound is taken into account.
    """

    bin_count: int
    frames_per_turn: int = DEFAULT_FRAMES_PER_TURN
    channels: int = DEFAULT_CHANNELS
    kernel_size: int = DEFAULT_KERNEL_SIZE
    dilations: tuple[int, ...] = DEFAULT_DILATIONS

    @property
    def input_channels(self) -> int:
        """The magnitude, and the turning the phase does whatever the sound is."""
        return 3 * self.bin_count


class ResidualBlock(nn.Module):
    """One dilated convolution over time, added back to what it was given.

    Phase advances frame by frame at a rate set by each bin's own frequency, so what a bin does next
    is mostly decided by its recent past. Stacking dilations widens that view geometrically, which
    reaches across a whole note's worth of frames at a small cost.
    """

    def __init__(self, channels: int, *, kernel_size: int, dilation: int) -> None:
        super().__init__()
        padding = dilation * (kernel_size - 1) // 2
        self.convolution = nn.Conv1d(channels, channels, kernel_size, padding=padding, dilation=dilation)
        self.normalization = nn.GroupNorm(num_groups=8, num_channels=channels)
        self.activation = nn.GELU()

    def forward(self, features: Tensor) -> Tensor:
        residual: Tensor = self.convolution(self.activation(self.normalization(features)))
        return features + residual


class PhaseModel(nn.Module):
    """Reads a magnitude spectrogram and says what phase each bin carries.

    The output is a point on the unit circle per bin per frame, so the network states an angle
    without ever representing one directly -- an angle wraps at its own boundary, and a network
    asked to produce one has to learn that the largest value and the smallest are neighbors.

    Frequencies enter as channels of a convolution over time. Each output channel therefore reads
    the whole spectrum at once, while its kernel reads a span of frames, which matches where the
    structure sits: a bin's phase is decided by its history and by what the rest of the spectrum is
    doing at that moment.
    """

    def __init__(self, shape: PhaseModelShape) -> None:
        super().__init__()
        self.shape = shape
        self.input_projection = nn.Conv1d(
            shape.input_channels, shape.channels, shape.kernel_size, padding=shape.kernel_size // 2
        )
        self.blocks = nn.Sequential(
            *(
                ResidualBlock(shape.channels, kernel_size=shape.kernel_size, dilation=dilation)
                for dilation in shape.dilations
            )
        )
        self.output_projection = nn.Conv1d(
            shape.channels, 2 * shape.bin_count, shape.kernel_size, padding=shape.kernel_size // 2
        )

    def forward(self, magnitude: Tensor, *, frame_offset: Tensor | None = None) -> Tensor:
        """The unit-circle phase for each bin, as ``(batch, 2, bins, frames)`` cosine and sine.

        `frame_offset` says where each example began in the recording it was cut from, so the
        turning handed to the network is the turning that example's own phase actually does.
        """
        turning = nominal_turning(magnitude, frames_per_turn=self.shape.frames_per_turn, frame_offset=frame_offset)
        reading = torch.cat((compress(magnitude), turning), dim=1)
        features = self.output_projection(self.blocks(self.input_projection(reading)))
        batch, _, frames = features.shape
        pair = features.reshape(batch, 2, self.shape.bin_count, frames)
        unit: Tensor = pair / pair.norm(dim=1, keepdim=True).clamp_min(MAGNITUDE_FLOOR)
        return unit


def compress(magnitude: Tensor) -> Tensor:
    """Read a magnitude spectrogram onto the scale a network learns from.

    Magnitudes span many orders of magnitude and a sample's level says nothing about its phase, so
    each example is read in decibels relative to its own peak and centered. That leaves a quiet
    sample and a loud one carrying the same picture.
    """
    peak = magnitude.amax(dim=(1, 2), keepdim=True).clamp_min(MAGNITUDE_FLOOR)
    decibels = 20.0 * torch.log10(magnitude.clamp_min(MAGNITUDE_FLOOR) / peak)
    compressed: Tensor = decibels.clamp_min(-DYNAMIC_RANGE_DB) / (DYNAMIC_RANGE_DB / 2.0) + 1.0
    return compressed


def nominal_turning(magnitude: Tensor, *, frames_per_turn: int, frame_offset: Tensor | None = None) -> Tensor:
    """The turning every bin's phase does from frame to frame before any sound is accounted for.

    A bin at frequency `k` advances by a fixed angle each hop, set by the analysis window alone. A
    convolution reads the same way wherever it is placed along time, so it cannot produce a field
    that turns at a rate depending on where in the signal a frame sits. Handing it that turning as
    something to read makes the answer expressible: what remains for the model to find is how far
    each bin departs from it, which is what the sound decides.

    `frame_offset` counts each example's first frame from the start of the recording it was cut
    from. Two crops of one sample taken at different moments carry phases that differ by a delay,
    which no listener hears and which this puts back where it belongs, so the model is asked for the
    phase its example really has rather than for one it has no way to know.
    """
    batch, bins, frames = magnitude.shape
    bin_index = torch.arange(bins, device=magnitude.device, dtype=magnitude.dtype)[None, :, None]
    frame_index = torch.arange(frames, device=magnitude.device, dtype=magnitude.dtype)[None, None, :]
    if frame_offset is None:
        start = torch.zeros(batch, device=magnitude.device, dtype=magnitude.dtype)
    else:
        start = frame_offset.to(device=magnitude.device, dtype=magnitude.dtype)
    angle = 2.0 * torch.pi * bin_index * (frame_index + start[:, None, None]) / frames_per_turn
    return torch.cat((torch.cos(angle), torch.sin(angle)), dim=1)
