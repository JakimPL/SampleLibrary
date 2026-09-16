from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter1d

from samplemorph.partials.channels import Channels
from samplemorph.partials.correspondence.assignment import assign_with_fades
from samplemorph.partials.correspondence.shifts import SHIFT_REACH_CENTS, SHIFT_STEP_CENTS, tallest_moves
from samplemorph.partials.places import PartialPlaces
from samplemorph.partials.profile import Correspondence

UNIT_TOLERANCE_CENTS: Final[float] = 50.0
PROPOSED_MOVES: Final[int] = 6
ALIKE_HELD: Final[float] = 0.05


@dataclass(frozen=True)
class GroupPairing:
    """Who meets whom when whole objects travel: the channels that pair, and the move each object makes.

    Shapes: `matched` is ``(pairs, 2)``, and `first_moves` and `second_moves` hold the move in cents
    that each channel's object travels by, NaN for a channel whose object meets nothing.
    """

    matched: NDArray[np.intp]
    first_moves: NDArray[np.float64]
    second_moves: NDArray[np.float64]


@dataclass(frozen=True)
class _Unit:
    """One object of a sound: the channels it holds, where they stand, and what each of them carries."""

    channels: NDArray[np.intp]
    cents: NDArray[np.float64]
    share: NDArray[np.float64]

    @property
    def carried(self) -> float:
        return float(self.share.sum())


@dataclass(frozen=True)
class _Meeting:
    """What it would cost two objects to travel together: the one move they take, and what it leaves behind."""

    move: float
    matched: NDArray[np.intp]
    missed: float


def pair_groups(
    first: Channels, second: Channels, *, places: tuple[PartialPlaces, PartialPlaces], correspondence: Correspondence
) -> GroupPairing:
    """Pair two sounds object by object, every object travelling by one move of its own.

    An object is a note's harmonics or a set of partials rising and falling together, and it travels
    whole: one move carries all of it, whether or not each channel finds a partner. Which object
    meets which is settled by one assignment over the objects themselves, so the morph has as many
    free choices as the sounds have objects rather than as many as they have partials, which is what
    keeps a tone from arriving as two.
    """
    here, there = _units(first, places[0]), _units(second, places[1])
    moves = np.full(first.channel_count, np.nan)
    countermoves = np.full(second.channel_count, np.nan)
    if not here or not there:
        return GroupPairing(matched=np.zeros((0, 2), dtype=np.intp), first_moves=moves, second_moves=countermoves)

    meetings = [[_meeting(one, two, correspondence=correspondence) for two in there] for one in here]
    met = assign_with_fades(
        np.array(
            [[_price(one, two, meeting=meetings[a][b]) for b, two in enumerate(there)] for a, one in enumerate(here)]
        ),
        first_fades=0.5 * correspondence.fade_price * np.array([one.carried for one in here]),
        second_fades=0.5 * correspondence.fade_price * np.array([two.carried for two in there]),
    )
    pairs = []
    for one, two in met:
        meeting = meetings[int(one)][int(two)]
        moves[here[int(one)].channels] = meeting.move
        countermoves[there[int(two)].channels] = meeting.move
        for row in meeting.matched:
            pairs.append((int(here[int(one)].channels[row[0]]), int(there[int(two)].channels[row[1]])))
    return GroupPairing(
        matched=np.array(pairs, dtype=np.intp).reshape(len(pairs), 2), first_moves=moves, second_moves=countermoves
    )


def _units(channels: Channels, places: PartialPlaces) -> list[_Unit]:
    """Every object a sound holds, the channels of one note that rise and fall together in each."""
    if channels.channel_count == 0:
        return []
    labels = channels.units
    return [
        _Unit(channels=found, cents=places.cents[found], share=places.share[found])
        for found in (np.flatnonzero(labels == label).astype(np.intp) for label in np.unique(labels))
    ]


def _price(one: _Unit, two: _Unit, *, meeting: _Meeting) -> float:
    """What it costs two objects to travel together, in the same fades a partial's journey is priced in."""
    return 0.5 * (one.carried + two.carried) * meeting.missed


def _meeting(one: _Unit, two: _Unit, *, correspondence: Correspondence) -> _Meeting:
    """The best the two objects can do: the move leaving the least of them behind, and who pairs under it.

    Which move to take and whether to take it are two questions. The move is the one explaining the
    most of the two objects, the shorter one taken where two explain within `ALIKE_HELD` of each
    other, which is what carries a sound onto its own octave rather than leaving three quarters of it
    standing. What that move then costs against fading is what the meeting is priced at.
    """
    tried = []
    for proposed in _proposals(one, two):
        move = _refined(one, two, move=proposed)
        matched = _within(one, two, move=move)
        tried.append((_held(one, two, matched=matched), move, matched))
    if not tried:
        return _Meeting(move=0.0, matched=np.zeros((0, 2), dtype=np.intp), missed=1.0)

    held, move, matched = max(tried, key=lambda found: (round(found[0] / ALIKE_HELD), -abs(found[1])))
    travel = (abs(move) / correspondence.travel_cents) ** correspondence.exponent
    return _Meeting(move=move, matched=matched, missed=travel + 1.0 - held)


def _refined(one: _Unit, two: _Unit, *, move: float) -> float:
    """The move read off the channels it pairs, which puts it where they stand rather than where the vote fell."""
    matched = _within(one, two, move=move)
    if matched.shape[0] == 0:
        return move
    apart = one.cents[matched[:, 0]] - two.cents[matched[:, 1]]
    weight = one.share[matched[:, 0]] + two.share[matched[:, 1]]
    order = np.argsort(apart)
    running = np.cumsum(weight[order])
    return float(apart[order][np.searchsorted(running, 0.5 * float(running[-1]))])


def _proposals(one: _Unit, two: _Unit) -> NDArray[np.float64]:
    """The moves most of two objects would take together, the heaviest few of them.

    A move is worth what the two channels proposing it carry between them, so a move two loud
    channels agree on outweighs one a loud channel shares with a quiet one, and a whole series
    agreeing outweighs any single pair.
    """
    apart = (one.cents[:, None] - two.cents).ravel()
    weights = (one.share[:, None] * two.share).ravel()
    within = np.abs(apart) <= SHIFT_REACH_CENTS
    if not within.any():
        return np.zeros(0)
    edges = np.arange(-SHIFT_REACH_CENTS, SHIFT_REACH_CENTS + SHIFT_STEP_CENTS, SHIFT_STEP_CENTS)
    voted, _ = np.histogram(apart[within], bins=edges, weights=weights[within])
    spread = gaussian_filter1d(voted, sigma=0.5 * UNIT_TOLERANCE_CENTS / SHIFT_STEP_CENTS, mode="constant")
    moves, _ = tallest_moves(spread, centers=0.5 * (edges[:-1] + edges[1:]), largest_count=PROPOSED_MOVES)
    return moves


def _within(one: _Unit, two: _Unit, *, move: float) -> NDArray[np.intp]:
    """Which channel of one object meets which of the other once the whole of it has moved by `move`."""
    return assign_with_fades(
        np.abs((one.cents[:, None] - move) - two.cents),
        first_fades=np.full(one.cents.shape[0], 0.5 * UNIT_TOLERANCE_CENTS),
        second_fades=np.full(two.cents.shape[0], 0.5 * UNIT_TOLERANCE_CENTS),
    )


def _held(one: _Unit, two: _Unit, *, matched: NDArray[np.intp]) -> float:
    """The share of two objects that finds a partner once they have met."""
    total = one.carried + two.carried
    if matched.shape[0] == 0 or total <= 0.0:
        return 0.0
    return float((one.share[matched[:, 0]].sum() + two.share[matched[:, 1]].sum()) / total)
