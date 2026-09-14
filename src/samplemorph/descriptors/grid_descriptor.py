from __future__ import annotations

from typing import Final

import torch
from torch import Tensor, nn

from samplemorph.descriptors.descriptor_shape import DescriptorShape

CHANNELS_PER_GROUP: Final[int] = 4
KERNEL_SIZE: Final[int] = 3


class GridDescriptor(nn.Module):
    """A small convolutional reader of a pooled canonical grid, answering with one unit vector.

    Each stage halves both axes, and the last is averaged over whatever remains of them, so the
    vector depends on what the spectrum looks like and on how it moves, and only weakly on where
    along the band axis it sits -- the alignment already put the strongest band in one place, and
    the pooling absorbs what the alignment missed. The canonical duration enters beside the pooled
    features, since a click and a pad can share a spectrum and differ in nothing else.
    """

    def __init__(self, shape: DescriptorShape) -> None:
        super().__init__()
        self.shape = shape
        stages: list[nn.Module] = []
        channels = 1
        for stage in range(shape.stage_count):
            next_channels = shape.width * 2**stage
            stages += [
                nn.Conv2d(channels, next_channels, KERNEL_SIZE, padding=KERNEL_SIZE // 2),
                nn.GroupNorm(next_channels // CHANNELS_PER_GROUP, next_channels),
                nn.GELU(),
                nn.MaxPool2d(2),
            ]
            channels = next_channels
        self.trunk = nn.Sequential(*stages)
        self.head = nn.Linear(channels + 1, shape.embedding_size)

    def forward(self, grid: Tensor, duration: Tensor) -> Tensor:
        # grid: (batch, bands, columns); duration: (batch,) -> (batch, embedding)
        features = self.trunk(grid[:, None]).mean(dim=(2, 3))
        combined = torch.cat([features, duration[:, None]], dim=1)
        return nn.functional.normalize(self.head(combined), dim=-1)
