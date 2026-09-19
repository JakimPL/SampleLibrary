from __future__ import annotations

from typing import Final

from torch import Tensor, nn
from torch.nn import functional

from samplemorph.features.shape import CHANNELS_PER_GROUP, FeatureShape

KERNEL_SIZE: Final[int] = 3
STAGE_FACTOR: Final[int] = 2


def padded(grids: Tensor, *, shape: FeatureShape) -> Tensor:
    """Grids extended with silence past their top band and their last column to the size every stage halves evenly.

    Shapes: ``(batch, bands, columns)`` in, ``(batch, padded bands, padded columns)`` out.
    """
    return functional.pad(
        grids,
        (0, shape.padded_time_columns - shape.time_columns, 0, shape.padded_band_count - shape.band_count),
    )


def downsampling_trunk(shape: FeatureShape) -> nn.Sequential:
    """The stages that read a padded grid down to the deepest map, each halving both axes and doubling the channels.

    Shapes: ``(batch, 1, padded bands, padded columns)`` in, ``(batch, *shape.deepest_map)`` out.
    """
    stages: list[nn.Module] = []
    channels = 1
    for stage in range(shape.stage_count):
        next_channels = shape.width * STAGE_FACTOR**stage
        stages += [
            nn.Conv2d(channels, next_channels, KERNEL_SIZE, stride=STAGE_FACTOR, padding=KERNEL_SIZE // 2),
            *_normalized(next_channels),
            nn.Conv2d(next_channels, next_channels, KERNEL_SIZE, padding=KERNEL_SIZE // 2),
            *_normalized(next_channels),
        ]
        channels = next_channels
    return nn.Sequential(*stages)


def upsampling_trunk(shape: FeatureShape) -> nn.Sequential:
    """The stages that grow the deepest map back to the padded grid, each doubling both axes.

    Every stage repeats cells and convolves the result, which spreads each output cell over the
    same number of inputs everywhere on the grid. Channels halve at every stage down to `width`.
    Shapes: ``(batch, *shape.deepest_map)`` in, ``(batch, width, padded bands, padded columns)`` out.
    """
    stages: list[nn.Module] = []
    channels = shape.deepest_channels
    for stage in reversed(range(shape.stage_count)):
        next_channels = shape.width * STAGE_FACTOR ** max(stage - 1, 0)
        stages += [
            nn.Upsample(scale_factor=STAGE_FACTOR, mode="nearest"),
            nn.Conv2d(channels, next_channels, KERNEL_SIZE, padding=KERNEL_SIZE // 2),
            *_normalized(next_channels),
            nn.Conv2d(next_channels, next_channels, KERNEL_SIZE, padding=KERNEL_SIZE // 2),
            *_normalized(next_channels),
        ]
        channels = next_channels
    return nn.Sequential(*stages)


def _normalized(channels: int) -> tuple[nn.Module, nn.Module]:
    return nn.GroupNorm(channels // CHANNELS_PER_GROUP, channels), nn.GELU()
