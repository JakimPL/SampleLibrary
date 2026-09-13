from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from samplemorph.vocoders.levels import floor_level

DEFAULT_CHANNELS: Final[int] = 48
DEFAULT_KERNEL_SIZE: Final[int] = 3
DEFAULT_DILATIONS: Final[tuple[int, ...]] = (1, 2, 4, 8, 1, 2, 4, 8)
ENTRY_KERNEL_SIZE: Final[int] = 5
GROUP_COUNT: Final[int] = 8


@dataclass(frozen=True)
class RestorerShape:
    """The capacity a restorer spends and how far along the frequency axis it looks.

    The network is convolutional in both directions, so one shape serves any transform length; the
    dilations widen its view along frequency, which is the axis the band averaging smoothed, and
    reach eight bins either side at the widest.
    """

    channels: int = DEFAULT_CHANNELS
    kernel_size: int = DEFAULT_KERNEL_SIZE
    dilations: tuple[int, ...] = DEFAULT_DILATIONS


class RestorerBlock(nn.Module):
    """One convolution dilated along frequency, added back to what it was given."""

    def __init__(self, channels: int, *, kernel_size: int, dilation: int) -> None:
        super().__init__()
        padding = (dilation * (kernel_size - 1) // 2, (kernel_size - 1) // 2)
        self.normalization = nn.GroupNorm(num_groups=GROUP_COUNT, num_channels=channels)
        self.convolution = nn.Conv2d(channels, channels, kernel_size, padding=padding, dilation=(dilation, 1))
        self.activation = nn.GELU()

    def forward(self, features: Tensor) -> Tensor:
        residual: Tensor = self.convolution(self.activation(self.normalization(features)))
        return features + residual


class Restorer(nn.Module):
    """Predicts the fine structure the band averaging removed from a magnitude, in decibels.

    The least-squares reading of a canonical grid is a smoothed magnitude: wherever several Fourier
    bins were averaged into one band, it spreads that band evenly over them. This network reads
    that magnitude and states, bin by bin, how far the real analysis of such a sound departs from
    the smooth one -- the harmonics and transients the corpus says a spectrum of this shape carries.
    Its output layer starts at zero, so an untrained restorer hands the least-squares reading
    through unchanged and training moves it away from that baseline only where the corpus says to.
    """

    def __init__(self, shape: RestorerShape) -> None:
        super().__init__()
        self.shape = shape
        self.input_projection = nn.Conv2d(1, shape.channels, ENTRY_KERNEL_SIZE, padding=ENTRY_KERNEL_SIZE // 2)
        self.blocks = nn.Sequential(
            *(
                RestorerBlock(shape.channels, kernel_size=shape.kernel_size, dilation=dilation)
                for dilation in shape.dilations
            )
        )
        self.output_projection = nn.Conv2d(
            shape.channels, 1, shape.kernel_size, padding=shape.kernel_size // 2, bias=True
        )
        nn.init.zeros_(self.output_projection.weight)
        nn.init.zeros_(torch.as_tensor(self.output_projection.bias))

    def forward(self, decibels: Tensor) -> Tensor:
        """The restored magnitude on the same scale, for ``(batch, bins, frames)`` decibels from `compress`."""
        features = self.blocks(self.input_projection(decibels[:, None]))
        residual: Tensor = self.output_projection(features)[:, 0]
        return decibels + residual


def compress(magnitude: NDArray[np.floating], *, peak: float, dynamic_range_db: float) -> NDArray[np.float32]:
    """Read a magnitude onto the scale the restorer learns on: decibels below `peak`, over the dynamic range.

    The peak reads as zero and anything `dynamic_range_db` or more below it as minus one, so a quiet
    sample and a loud one carry the same picture and the target of a pair is read against the same
    peak as its input. The range is the grid's own, so the floor the restorer reads is the floor
    the canonical image already imposed.
    """
    floor = floor_level(peak, dynamic_range_db=dynamic_range_db)
    decibels: NDArray[np.float32] = (20.0 * np.log10(np.maximum(magnitude, floor) / peak) / dynamic_range_db).astype(
        np.float32
    )
    return decibels


def expand(decibels: NDArray[np.floating], *, peak: float, dynamic_range_db: float) -> NDArray[np.float64]:
    """Read the restorer's output back into a linear magnitude under the peak it was compressed against."""
    magnitude: NDArray[np.float64] = peak * 10.0 ** (decibels.astype(np.float64) * dynamic_range_db / 20.0)
    return magnitude
