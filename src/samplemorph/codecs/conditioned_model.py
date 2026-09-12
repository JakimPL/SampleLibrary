from __future__ import annotations

import math
from enum import StrEnum
from typing import Final

import torch
from pydantic import BaseModel
from torch import Tensor, nn

from samplecore.models.base import FROZEN


class ResidualLayout(StrEnum):
    """How the residual is laid out at the bottleneck.

    `VECTOR` reads the whole bottleneck into one vector, so every residual number can speak for any
    band at any moment. `MAP` keeps the bottleneck's map and holds a few numbers at each of its
    cells, so a residual number speaks for the bands and the moment of the cell it sits in.
    """

    VECTOR = "vector"
    MAP = "map"


DEFAULT_RESIDUAL_SIZE: Final[int] = 64
DEFAULT_RESIDUAL_LAYOUT: Final[ResidualLayout] = ResidualLayout.VECTOR
DEFAULT_CODEC_WIDTH: Final[int] = 16
STAGE_COUNT: Final[int] = 4
BAND_STRIDE: Final[int] = 4
TIME_STRIDES: Final[tuple[int, ...]] = (1, 2, 2, 2)
KERNEL: Final[tuple[int, int]] = (5, 3)
CHANNELS_PER_GROUP: Final[int] = 4


class ConditionedCodecShape(BaseModel):
    """The dimensions that fix a conditioned codec, recorded beside its weights.

    `residual_size` counts the numbers the residual holds at each of its positions: the vector
    layout has one position, the map layout one per bottleneck cell.
    """

    model_config = FROZEN

    band_count: int
    time_columns: int
    descriptor_size: int
    residual_size: int = DEFAULT_RESIDUAL_SIZE
    width: int = DEFAULT_CODEC_WIDTH
    layout: ResidualLayout = DEFAULT_RESIDUAL_LAYOUT

    @property
    def band_stride(self) -> int:
        return int(BAND_STRIDE**STAGE_COUNT)

    @property
    def padded_band_count(self) -> int:
        """The band axis rounded up to what the stages divide evenly, the extra rows resting on silence."""
        return -(-self.band_count // self.band_stride) * self.band_stride

    @property
    def bottleneck_shape(self) -> tuple[int, int, int]:
        """(channels, bands, columns) at the narrowest stage."""
        columns = self.time_columns
        for stride in TIME_STRIDES:
            columns //= stride
        return self.width * 2 ** (STAGE_COUNT - 1), self.padded_band_count // self.band_stride, columns

    @property
    def residual_shape(self) -> tuple[int, ...]:
        """The residual's own axes: `(residual_size,)` as a vector, `(residual_size, bands, columns)` as a map."""
        if self.layout is ResidualLayout.MAP:
            _channels, bands, columns = self.bottleneck_shape
            return self.residual_size, bands, columns
        return (self.residual_size,)

    @property
    def residual_length(self) -> int:
        """How many numbers the residual holds once flattened, which is what a latent carries."""
        return math.prod(self.residual_shape)


class FeatureModulation(nn.Module):
    """Scales and shifts a stage's channels by what the descriptor says, which is how the sound's identity enters."""

    def __init__(self, descriptor_size: int, channels: int) -> None:
        super().__init__()
        self.affine = nn.Linear(descriptor_size, 2 * channels)

    def forward(self, features: Tensor, descriptor: Tensor) -> Tensor:
        scale, shift = self.affine(descriptor).chunk(2, dim=-1)
        modulated: Tensor = features * (1.0 + scale[:, :, None, None]) + shift[:, :, None, None]
        return modulated


class _Stage(nn.Module):
    def __init__(self, convolution: nn.Module, channels: int, descriptor_size: int) -> None:
        super().__init__()
        self.convolution = convolution
        self.normalization = nn.GroupNorm(channels // CHANNELS_PER_GROUP, channels)
        self.modulation = FeatureModulation(descriptor_size, channels)

    def forward(self, features: Tensor, descriptor: Tensor) -> Tensor:
        # pylint: disable-next=not-callable
        return nn.functional.gelu(self.modulation(self.normalization(self.convolution(features)), descriptor))


class ConditionedCodecModel(nn.Module):
    """A convolutional autoencoder of the canonical grid whose every stage is told what the sound is.

    The descriptor enters both halves, so the residual only has to carry what the descriptor does
    not say -- the particular realization of a sound whose kind is already known. The residual is
    read as a Gaussian, mean and log-variance, so that a point between two residuals still decodes
    to something. The band axis is padded with silence up to what the strides divide, and cropped
    back on the way out.
    """

    def __init__(self, shape: ConditionedCodecShape) -> None:
        super().__init__()
        self.shape = shape
        channels = [shape.width * 2**stage for stage in range(STAGE_COUNT)]
        self.encoder_stages = nn.ModuleList()
        incoming = 1
        for outgoing, time_stride in zip(channels, TIME_STRIDES, strict=True):
            self.encoder_stages.append(
                _Stage(
                    nn.Conv2d(
                        incoming,
                        outgoing,
                        KERNEL,
                        stride=(BAND_STRIDE, time_stride),
                        padding=(KERNEL[0] // 2, KERNEL[1] // 2),
                    ),
                    outgoing,
                    shape.descriptor_size,
                )
            )
            incoming = outgoing
        bottleneck_channels, bottleneck_bands, bottleneck_columns = shape.bottleneck_shape
        self.to_residual: nn.Module
        self.from_residual: nn.Module
        if shape.layout is ResidualLayout.MAP:
            self.to_residual = nn.Conv2d(bottleneck_channels, 2 * shape.residual_size, 1)
            self.from_residual = nn.Conv2d(shape.residual_size + shape.descriptor_size, bottleneck_channels, 1)
        else:
            flat = bottleneck_channels * bottleneck_bands * bottleneck_columns
            self.to_residual = nn.Linear(flat, 2 * shape.residual_size)
            self.from_residual = nn.Linear(shape.residual_size + shape.descriptor_size, flat)
        self.decoder_stages = nn.ModuleList()
        incoming = bottleneck_channels
        for stage in reversed(range(STAGE_COUNT)):
            outgoing = channels[stage - 1] if stage > 0 else shape.width
            time_stride = TIME_STRIDES[stage]
            self.decoder_stages.append(
                _Stage(
                    nn.ConvTranspose2d(
                        incoming, outgoing, (BAND_STRIDE, time_stride), stride=(BAND_STRIDE, time_stride)
                    ),
                    outgoing,
                    shape.descriptor_size,
                )
            )
            incoming = outgoing
        self.to_grid = nn.Conv2d(shape.width, 1, KERNEL, padding=(KERNEL[0] // 2, KERNEL[1] // 2))

    def encode(self, grid: Tensor, descriptor: Tensor) -> tuple[Tensor, Tensor]:
        """The residual's mean and log-variance for each grid, read beside its descriptor, in the residual's own shape."""
        # grid: (batch, bands, columns) -> (batch, 1, padded bands, columns)
        features = nn.functional.pad(grid, (0, 0, 0, self.shape.padded_band_count - self.shape.band_count))[:, None]
        for stage in self.encoder_stages:
            features = stage(features, descriptor)
        return self._read_residual(features)

    def decode(self, residual: Tensor, descriptor: Tensor) -> Tensor:
        """The grid a residual and a descriptor describe, in the grid's own unit interval."""
        features = self._write_bottleneck(residual, descriptor)
        for stage in self.decoder_stages:
            features = stage(features, descriptor)
        grid: Tensor = torch.sigmoid(self.to_grid(features))[:, 0, : self.shape.band_count]
        return grid

    def forward(self, grid: Tensor, descriptor: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """Reconstruct each grid through a residual drawn from its posterior while training, its mean otherwise."""
        mean, log_variance = self.encode(grid, descriptor)
        residual = mean + torch.randn_like(mean) * torch.exp(0.5 * log_variance) if self.training else mean
        return self.decode(residual, descriptor), mean, log_variance

    def _read_residual(self, features: Tensor) -> tuple[Tensor, Tensor]:
        if self.shape.layout is ResidualLayout.MAP:
            # (batch, 2 * residual, bands, columns) -> two maps of (batch, residual, bands, columns)
            mean, log_variance = self.to_residual(features).chunk(2, dim=1)
            return mean, log_variance
        mean, log_variance = self.to_residual(features.flatten(1)).chunk(2, dim=-1)
        return mean, log_variance

    def _write_bottleneck(self, residual: Tensor, descriptor: Tensor) -> Tensor:
        bottleneck_channels, bottleneck_bands, bottleneck_columns = self.shape.bottleneck_shape
        if self.shape.layout is ResidualLayout.MAP:
            # descriptor: (batch, size) laid over every cell -> (batch, size, bands, columns)
            spread = descriptor[:, :, None, None].expand(-1, -1, bottleneck_bands, bottleneck_columns)
            features: Tensor = self.from_residual(torch.cat([residual, spread], dim=1))
            return features
        features = self.from_residual(torch.cat([residual, descriptor], dim=-1))
        return features.view(-1, bottleneck_channels, bottleneck_bands, bottleneck_columns)
