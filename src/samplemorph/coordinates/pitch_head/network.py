from __future__ import annotations

import torch
from torch import Tensor, nn

from samplemorph.coordinates.pitch_head.shape import PitchHeadShape

LEAKY_SLOPE = 0.1


class ToeplitzLinear(nn.Module):
    """Maps the bins read onto the bins answered with one weight per offset between them.

    Every output bin reads its inputs through the same weights, offset by where it sits, so moving
    the input along the bin axis moves the answer with it. That is the one property a pitch has to
    have, and it holds here by the shape of the map rather than by what the weights learn. It is the
    Toeplitz layer of PESTO (Riou et al., 2023), written as the correlation it is.
    """

    def __init__(self, shape: PitchHeadShape) -> None:
        super().__init__()
        self.shape = shape
        self.correlation = nn.Conv1d(
            shape.channels[-1],
            1,
            shape.toeplitz_kernel_size,
            padding=shape.output_bins - 1,
            bias=False,
        )
        with torch.no_grad():
            self.correlation.weight.uniform_(-1.0, 1.0).div_((shape.channels[-1] * shape.band_count) ** 0.5)

    def forward(self, features: Tensor) -> Tensor:
        # features: (batch, channels, band count) -> (batch, output bins)
        answered: Tensor = self.correlation(features)[:, 0]
        return answered


class PitchNetwork(nn.Module):
    """Reads one constant-Q frame and answers where its pitch lies, as a distribution over pitch bins.

    Convolutions along the bin axis read the shape of a harmonic series wherever it stands, and the
    Toeplitz layer that follows turns what they find into the answer at the place they found it.
    Each layer is normalized over the bins it reads, whose statistics a move along the axis leaves
    alone, so the whole network answers a moved frame with a moved distribution.
    """

    def __init__(self, shape: PitchHeadShape) -> None:
        super().__init__()
        self.shape = shape
        layers: list[nn.Module] = []
        for reading, writing in zip((1, *shape.channels[:-1]), shape.channels, strict=True):
            layers += [
                nn.Conv1d(reading, writing, shape.kernel_size, padding=shape.kernel_size // 2),
                nn.LayerNorm(shape.band_count),
                nn.LeakyReLU(LEAKY_SLOPE),
            ]
        self.body = nn.Sequential(*layers)
        self.output = ToeplitzLinear(shape)

    def forward(self, frames: Tensor) -> Tensor:
        # frames: (batch, band count) -> (batch, output bins), each row summing to one
        distributions: Tensor = torch.softmax(self.output(self.body(frames[:, None])), dim=-1)
        return distributions
