from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

import numpy as np
from numpy.typing import NDArray

from samplecore.waveform import heard_at_rate
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono

End = TypeVar("End")


@dataclass(frozen=True)
class HeardMono:
    """One end of a pair as it sounds in the pair's frame: prepared frames played at `rate_hz`."""

    mono: PreparedMono
    rate_hz: float


class Route(Protocol[End]):
    """A way from two sounds to any point between them.

    `prepare` reads one end once into whatever the route renders from, so a path over many weights
    pays the reading once per end; `render` returns the frames at `weight` between two prepared
    ends, played at the rate both ends were heard at, with weight 0 and 1 rendering each end.
    """

    def prepare(self, heard: HeardMono) -> End: ...

    def render(self, first: End, second: End, *, weight: float) -> NDArray[np.float64]: ...


class PreparedPair(Protocol):
    """Two ends prepared by one route, ready to render any weight between them."""

    def render(self, *, weight: float) -> NDArray[np.float64]: ...


@dataclass(frozen=True)
class RoutePair(Generic[End]):
    """Two ends one route prepared, beside the route that renders between them."""

    route: Route[End]
    first: End
    second: End

    def render(self, *, weight: float) -> NDArray[np.float64]:
        return self.route.render(self.first, self.second, weight=weight)


def prepare_pair(route: Route[End], first: HeardMono, second: HeardMono) -> RoutePair[End]:
    return RoutePair(route=route, first=route.prepare(first), second=route.prepare(second))


def hear_in_frame(pcm: NDArray[np.float64], *, rate_hz: float, target_rate_hz: float) -> HeardMono:
    """Stored frames heard at `rate_hz`, resampled so that played at `target_rate_hz` they sound the same."""
    return HeardMono(
        mono=prepare_mono(heard_at_rate(pcm, playback_rate_hz=rate_hz, stored_rate_hz=target_rate_hz)),
        rate_hz=target_rate_hz,
    )
