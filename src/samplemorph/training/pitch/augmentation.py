from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import torch
from torch import Tensor

from samplemorph.training.pitch.settings import AugmentationSettings

FRAME_CEILING: Final[float] = 1.0
FRAME_FLOOR: Final[float] = 0.0


@dataclass(frozen=True)
class FrameAugmentation:
    """Draws what one view of a frame has done to it: a body to sound through, cut registers, and a noise floor.

    Every change is a gain over the bin axis, which moves no partial, so two views of one frame
    differ in everything a pitch is not. The frame is read back onto its own scale afterwards, its
    loudest bin at one and its floor at zero, as the analysis stores it.
    """

    settings: AugmentationSettings
    frame_range_db: float

    def __call__(self, frames: Tensor) -> Tensor:
        # frames: (batch, bands) -> (batch, bands)
        bins = torch.arange(frames.shape[1], device=frames.device, dtype=frames.dtype)
        gain_db = self._envelope(frames, bins=bins) + self._cuts(frames, bins=bins)
        lifted = frames + gain_db / self.frame_range_db
        floors = self.settings.noise_floor * self._drawn(frames)
        return _renormalized(torch.maximum(lifted, floors))

    def _envelope(self, frames: Tensor, *, bins: Tensor) -> Tensor:
        """A smooth gain drawn by the first few cosines over the bin axis, scaled to a drawn depth."""
        orders = torch.arange(1, self.settings.envelope_orders + 1, device=frames.device, dtype=frames.dtype)
        basis = torch.cos(math.pi * orders[:, None] * (bins[None, :] + 0.5) / bins.shape[0])
        coefficients = torch.rand(
            frames.shape[0], self.settings.envelope_orders, device=frames.device, dtype=frames.dtype
        )
        shape = (2.0 * coefficients - 1.0) @ basis
        depth = self.settings.envelope_db * self._drawn(frames)
        return depth * shape / shape.abs().amax(dim=1, keepdim=True).clamp_min(torch.finfo(frames.dtype).tiny)

    def _cuts(self, frames: Tensor, *, bins: Tensor) -> Tensor:
        """The gain of a shelf cutting the bins under a drawn bin away, and one cutting those over another."""
        band_count = bins.shape[0]
        lowest = band_count * 0.5 * self._drawn(frames)
        highest = band_count * (0.5 + 0.5 * self._drawn(frames))
        ramp = float(self.settings.cut_ramp_bins)
        under = ((lowest - bins[None, :]) / ramp).clamp(0.0, 1.0)
        over = ((bins[None, :] - highest) / ramp).clamp(0.0, 1.0)
        return -self.settings.cut_depth_db * (self._drawn(frames) * under + self._drawn(frames) * over)

    def _drawn(self, frames: Tensor) -> Tensor:
        """One number in ``[0, 1]`` per frame of the batch, drawn afresh. Shape: ``(batch, 1)``."""
        return torch.rand(frames.shape[0], 1, device=frames.device, dtype=frames.dtype)


def _renormalized(frames: Tensor) -> Tensor:
    """Frames read back onto the analysis's own scale: the loudest bin at one, and nothing under the floor."""
    return (frames - frames.amax(dim=1, keepdim=True) + FRAME_CEILING).clamp(FRAME_FLOOR, FRAME_CEILING)
