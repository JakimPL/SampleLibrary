from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.correspondence.partials import ordered_pairs, partial_voices
from samplemorph.partials.profile import Correspondence, NoCorrespondence, OrderedPartials
from samplemorph.partials.tracks import PartialTracks


@dataclass(frozen=True)
class ChannelPairing:
    """Who meets whom between two sounds: the partials that travel together, and those that travel alone.

    Shapes: `matched` is ``(pairs, 2)``, a partial of each sound per row, and both `first_alone` and
    `second_alone` hold the partials of one sound that meet nothing in the other.
    """

    matched: NDArray[np.intp]
    first_alone: NDArray[np.intp]
    second_alone: NDArray[np.intp]

    @property
    def pair_count(self) -> int:
        return int(self.matched.shape[0])


def pair_partials(first: PartialTracks, second: PartialTracks, *, correspondence: Correspondence) -> ChannelPairing:
    """Pair two sounds' partials the way a profile's correspondence says to.

    The pairing is read once for a pair of sounds and holds at every weight and every frame between
    them, which is what lets a partial glide along one path from end to end.
    """
    match correspondence:
        case OrderedPartials():
            return _pairing(ordered_pairs(partial_voices(first), partial_voices(second)), first=first, second=second)
        case NoCorrespondence():
            return _pairing(np.zeros((0, 2), dtype=np.intp), first=first, second=second)


def _pairing(matched: NDArray[np.intp], *, first: PartialTracks, second: PartialTracks) -> ChannelPairing:
    return ChannelPairing(
        matched=matched,
        first_alone=_left_out(matched[:, 0], count=first.track_count),
        second_alone=_left_out(matched[:, 1], count=second.track_count),
    )


def _left_out(taken: NDArray[np.intp], *, count: int) -> NDArray[np.intp]:
    met = np.zeros(count, dtype=bool)
    met[taken] = True
    return np.flatnonzero(~met).astype(np.intp)
