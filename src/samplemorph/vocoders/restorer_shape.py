from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DEFAULT_CHANNELS: Final[int] = 48
DEFAULT_KERNEL_SIZE: Final[int] = 3
DEFAULT_DILATIONS: Final[tuple[int, ...]] = (1, 2, 4, 8, 1, 2, 4, 8)
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
