from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.channels import Channels
from samplemorph.partials.correspondence.assignment import assign_with_fades
from samplemorph.partials.correspondence.cost import travel_penalty
from samplemorph.partials.correspondence.groups import pair_groups
from samplemorph.partials.correspondence.shifts import AgreedShifts, agreed_shifts, no_shifts
from samplemorph.partials.places import PartialPlaces, partial_places
from samplemorph.partials.profile import Correspondence, CorrespondenceUnit

SETTLING_ROUNDS: Final[int] = 2


@dataclass(frozen=True)
class ChannelPairing:
    """Who meets whom between two sounds: the channels that travel together, and those that travel alone.

    Shapes: `matched` is ``(pairs, 2)``, a channel of each sound per row, both `first_alone` and
    `second_alone` hold the channels of one sound meeting nothing in the other, and `first_moves` and
    `second_moves` hold the move in cents a channel's object travels by, NaN where it travels alone
    and holds its own pitch.
    """

    matched: NDArray[np.intp]
    first_alone: NDArray[np.intp]
    second_alone: NDArray[np.intp]
    first_moves: NDArray[np.float64]
    second_moves: NDArray[np.float64]

    @property
    def pair_count(self) -> int:
        return int(self.matched.shape[0])


def pair_channels(first: Channels, second: Channels, *, correspondence: Correspondence) -> ChannelPairing:
    """Pair two sounds' channels, every channel free to travel to any other or to fade where it stands.

    One assignment settles the whole pair of sounds at once: each channel carries what it is worth of
    its own sound, meeting costs that weight times the price the correspondence puts on the travel,
    and fading costs it the fade price. The least total price over both sounds is the pairing taken,
    so a channel travels an octave where the rest of the sound travels an octave beside it, and fades
    where no partner comes to less than the fade price.

    The first reading pairs by pitch, loudness and time alone. The moves it makes are then read back
    as the intervals the two sounds agree on, and the pairing is read again knowing them, which is
    what settles a chord onto one voice leading and a harmonic series onto one interval. The pairing
    is read once for a pair of sounds and holds at every weight and every frame between them, which
    is what lets a partial glide along one path from end to end.
    """
    here, there = partial_places(first.tracks), partial_places(second.tracks)
    if correspondence.unit is CorrespondenceUnit.GROUPS:
        grouped = pair_groups(first, second, places=(here, there), correspondence=correspondence)
        return _pairing(grouped.matched, first=first, second=second, moves=(grouped.first_moves, grouped.second_moves))

    matched = _assigned(here, there, shifts=no_shifts(here.count), correspondence=correspondence)
    for _ in range(SETTLING_ROUNDS):
        shifts = agreed_shifts(
            here,
            there,
            matched=matched,
            lines=first.lines,
            correspondence=correspondence,
        )
        if shifts.count == 0:
            break
        matched = _assigned(here, there, shifts=shifts, correspondence=correspondence)
    return _pairing(
        matched,
        first=first,
        second=second,
        moves=(np.full(first.channel_count, np.nan), np.full(second.channel_count, np.nan)),
    )


def _pairing(
    matched: NDArray[np.intp],
    *,
    first: Channels,
    second: Channels,
    moves: tuple[NDArray[np.float64], NDArray[np.float64]],
) -> ChannelPairing:
    return ChannelPairing(
        matched=matched,
        first_alone=_left_out(matched[:, 0], count=first.channel_count),
        second_alone=_left_out(matched[:, 1], count=second.channel_count),
        first_moves=moves[0],
        second_moves=moves[1],
    )


def _assigned(
    first: PartialPlaces, second: PartialPlaces, *, shifts: AgreedShifts, correspondence: Correspondence
) -> NDArray[np.intp]:
    """The pairing that costs the two sounds least, every channel free to travel or to fade at its own price."""
    return assign_with_fades(
        0.5
        * (first.share[:, None] + second.share)
        * travel_penalty(first, second, shifts=shifts, correspondence=correspondence),
        first_fades=0.5 * first.share * correspondence.fade_price,
        second_fades=0.5 * second.share * correspondence.fade_price,
    )


def _left_out(taken: NDArray[np.intp], *, count: int) -> NDArray[np.intp]:
    met = np.zeros(count, dtype=bool)
    met[taken] = True
    return np.flatnonzero(~met).astype(np.intp)
