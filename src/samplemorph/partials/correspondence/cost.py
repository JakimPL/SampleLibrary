from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.correspondence.shifts import AgreedShifts
from samplemorph.partials.profile import Correspondence
from samplemorph.partials.voices import PartialVoices


def travel_penalty(
    first: PartialVoices, second: PartialVoices, *, shifts: AgreedShifts, correspondence: Correspondence
) -> NDArray[np.float64]:
    """What it would cost every pair of partials to travel together, counted in fades.

    A pair pays for four things, each reaching 1 where it alone is worth a whole fade: the distance it
    covers, how far that distance stands from the move the pair is held to, how differently the two
    stand in loudness, and how little of their lives they share. A pair travels when the four together
    come to less than the fade price, so distance prices a meeting rather than forbidding one, which
    is what carries two sounds a fifth apart into each other.
    Shape: the result is ``(first partials, second partials)``.
    """
    apart = first.cents[:, None] - second.cents
    return (
        (np.abs(apart) / correspondence.travel_cents) ** correspondence.exponent
        + (_drift(apart, shifts=shifts) / correspondence.drift_cents) ** correspondence.exponent
        + correspondence.level_weight * _loudness_apart(first, second)
        + correspondence.lifetime_weight * (1.0 - _overlap(first, second))
    )


def _drift(apart: NDArray[np.float64], *, shifts: AgreedShifts) -> NDArray[np.float64]:
    """How far each pair's own move stands from the move it is held to.

    A channel whose line travels by one move is held to that move, which keeps a harmonic series
    together where another series crosses it at one frequency, and a channel standing on its own is
    held to the nearest of the moves the two sounds agree on. Shapes: `apart` is
    ``(first partials, second partials)`` and so is the result.
    """
    if shifts.count == 0:
        return np.zeros_like(apart)
    own = shifts.by_channel[:, None]
    drift: NDArray[np.float64] = np.where(
        np.isnan(own), np.abs(apart[..., None] - shifts.cents).min(axis=-1), np.abs(apart - own)
    )
    return drift


def _loudness_apart(first: PartialVoices, second: PartialVoices) -> NDArray[np.float64]:
    """How differently two partials stand in loudness, 0 where they stand alike and 1 where one of them is silent."""
    here, there = first.loudness[:, None], second.loudness
    total = here + there
    apart: NDArray[np.float64] = np.abs(here - there) / np.where(total > 0.0, total, 1.0)
    return apart


def _overlap(first: PartialVoices, second: PartialVoices) -> NDArray[np.float64]:
    """The share of the shorter of two lives that the two partials are heard through together."""
    start = np.maximum(first.onset[:, None], second.onset)
    end = np.minimum(first.offset[:, None], second.offset)
    shorter = np.minimum(first.lifetime[:, None], second.lifetime)
    shared: NDArray[np.float64] = np.where(
        shorter > 0.0,
        np.maximum(end - start, 0.0) / np.where(shorter > 0.0, shorter, 1.0),
        (end >= start).astype(float),
    )
    return shared
