from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.channels import Channels
from samplemorph.partials.correspondence.notes import harmonic_pairs, note_pairs
from samplemorph.partials.correspondence.partials import nearest_pairs, ordered_pairs
from samplemorph.partials.profile import (
    Correspondence,
    NearestPartials,
    NoCorrespondence,
    NotesCorrespondence,
    OrderedPartials,
)
from samplemorph.partials.voices import partial_voices


@dataclass(frozen=True)
class ChannelPairing:
    """Who meets whom between two sounds: the channels that travel together, and those that travel alone.

    Shapes: `matched` is ``(pairs, 2)``, a channel of each sound per row, and both `first_alone` and
    `second_alone` hold the channels of one sound meeting nothing in the other.
    """

    matched: NDArray[np.intp]
    first_alone: NDArray[np.intp]
    second_alone: NDArray[np.intp]

    @property
    def pair_count(self) -> int:
        return int(self.matched.shape[0])


def pair_channels(first: Channels, second: Channels, *, correspondence: Correspondence) -> ChannelPairing:
    """Pair two sounds' channels the way a profile's correspondence says to.

    The pairing is read once for a pair of sounds and holds at every weight and every frame between
    them, which is what lets a partial glide along one path from end to end.
    """
    match correspondence:
        case NotesCorrespondence():
            met = harmonic_pairs(
                first,
                second,
                notes=note_pairs(
                    first, second, cap_semitones=correspondence.cap_semitones, exponent=correspondence.exponent
                ),
            )
            free = nearest_pairs(
                partial_voices(first.tracks),
                partial_voices(second.tracks),
                cap_cents=correspondence.cap_cents,
                taken=(met[:, 0], met[:, 1]),
            )
            return _pairing(np.concatenate((met, free)), first=first, second=second)
        case NearestPartials():
            return _pairing(
                nearest_pairs(
                    partial_voices(first.tracks),
                    partial_voices(second.tracks),
                    cap_cents=correspondence.cap_cents,
                    taken=(np.zeros(0, dtype=np.intp), np.zeros(0, dtype=np.intp)),
                ),
                first=first,
                second=second,
            )
        case OrderedPartials():
            return _pairing(
                ordered_pairs(partial_voices(first.tracks), partial_voices(second.tracks)), first=first, second=second
            )
        case NoCorrespondence():
            return _pairing(np.zeros((0, 2), dtype=np.intp), first=first, second=second)


def _pairing(matched: NDArray[np.intp], *, first: Channels, second: Channels) -> ChannelPairing:
    return ChannelPairing(
        matched=matched,
        first_alone=_left_out(matched[:, 0], count=first.channel_count),
        second_alone=_left_out(matched[:, 1], count=second.channel_count),
    )


def _left_out(taken: NDArray[np.intp], *, count: int) -> NDArray[np.intp]:
    met = np.zeros(count, dtype=bool)
    met[taken] = True
    return np.flatnonzero(~met).astype(np.intp)
