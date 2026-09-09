from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.codecs import SampleCodec
from samplemorph.images import SampleLatent
from samplemorph.measurement.comparison import grid_distance
from samplemorph.morphers import Morpher, MorphWeights

DEFAULT_MORPH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)
# The grid spans this many decibels between its floor and its peak, which is what turns a cell
# back into a magnitude a spread can be read from.
GRID_DYNAMIC_RANGE_DB: Final[float] = 100.0


@dataclass(frozen=True)
class MorphEndpoint:
    """One end of a morph: the sample it starts or arrives at, and that sample's own latent."""

    sample_hash: str
    latent: SampleLatent


@dataclass(frozen=True)
class MorphStep:
    """One point along a morph: how far its decoded grid sits from each endpoint, and how spread its spectrum is.

    Two readings guard against the two ways a path can fail to be a sound. `spread_excess` is the
    step's spectral spread over the larger of the two endpoints' own: two sounds played at once
    carry both patterns and spread wider than either. `energy_share` is the step's energy over the
    mean of the endpoints': a straight line through a grid of decibels thins out whatever the two
    sounds do not share, so a step carrying a fraction of the energy is the shadow of both rather
    than a sound between them. A sound holds its energy and spreads no wider.
    """

    weight: float
    distance_to_first: float
    distance_to_second: float
    spread_excess: float
    energy_share: float


@dataclass(frozen=True)
class MorphPlausibility:
    """Whether travelling between two samples produces a path or a wash.

    A representation where interpolation means something moves the result away from the first
    sample and toward the second, step by step. A codec that instead blends the two keeps the
    result near both throughout, and one that leaves the manifold sends the distance to both
    endpoints climbing at once. Reading the two distance profiles together tells those apart, and
    it is the standing guard against rebuilding a two-signal crossfade under a better name.
    """

    first_hash: str
    second_hash: str
    steps: tuple[MorphStep, ...]

    @property
    def travels_away_from_the_first(self) -> bool:
        return _rises(tuple(step.distance_to_first for step in self.steps))

    @property
    def travels_toward_the_second(self) -> bool:
        return _falls(tuple(step.distance_to_second for step in self.steps))

    @property
    def is_monotone(self) -> bool:
        """Whether the path leaves one endpoint and reaches the other without doubling back."""
        return self.travels_away_from_the_first and self.travels_toward_the_second

    @property
    def largest_spread_excess(self) -> float:
        """How much wider than either endpoint the widest step spreads; two sounds at once show here."""
        return max(step.spread_excess for step in self.steps)

    @property
    def smallest_energy_share(self) -> float:
        """The least of the energy any step keeps; a path thinning out along the way shows here."""
        return min(step.energy_share for step in self.steps)

    @property
    def furthest_excursion(self) -> float:
        """How far past both endpoints the path strays, at its worst step.

        A step sitting further from both endpoints than they sit from each other has left the space
        real samples occupy, which is what a decoded latent does when interpolation carries it off
        the manifold.
        """
        endpoint_distance = self.steps[0].distance_to_second
        return max(min(step.distance_to_first, step.distance_to_second) for step in self.steps) - endpoint_distance


def morph_plausibility(
    first: MorphEndpoint,
    second: MorphEndpoint,
    *,
    codec: SampleCodec,
    morpher: Morpher,
    weights: tuple[float, ...] = DEFAULT_MORPH_WEIGHTS,
) -> MorphPlausibility:
    """Decode a morph at each weight and measure its grid against both endpoints' own.

    Raises:
        ValueError: fewer than two weights were offered, leaving no path to describe.
    """
    if len(weights) < 2:
        raise ValueError(f"a morph path asks for at least two weights, got {len(weights)}")

    first_grid = codec.decode(first.latent).grid
    second_grid = codec.decode(second.latent).grid
    endpoint_spread = max(spectral_spread(first_grid), spectral_spread(second_grid))
    endpoint_energy = 0.5 * (grid_energy(first_grid) + grid_energy(second_grid))
    steps = []
    for weight in weights:
        morphed = morpher.morph(first.latent, second.latent, weights=MorphWeights.uniform(weight))
        decoded = codec.decode(morphed).grid
        steps.append(
            MorphStep(
                weight=weight,
                distance_to_first=grid_distance(decoded, first_grid),
                distance_to_second=grid_distance(decoded, second_grid),
                spread_excess=spectral_spread(decoded) - endpoint_spread,
                energy_share=grid_energy(decoded) / endpoint_energy if endpoint_energy > 0.0 else 0.0,
            )
        )
    return MorphPlausibility(first_hash=first.sample_hash, second_hash=second.sample_hash, steps=tuple(steps))


def grid_magnitudes(grid: NDArray[np.float64]) -> NDArray[np.float64]:
    """A grid's cells read back as magnitudes, the floor reading as nothing at all."""
    magnitude: NDArray[np.float64] = 10.0 ** (GRID_DYNAMIC_RANGE_DB * (grid - 1.0) / 20.0)
    return np.where(grid > 0.0, magnitude, 0.0)


def grid_energy(grid: NDArray[np.float64]) -> float:
    """The energy a grid carries, summed over its magnitudes squared."""
    return float((grid_magnitudes(grid) ** 2).sum())


def spectral_spread(grid: NDArray[np.float64]) -> float:
    """How widely a grid's energy is spread across its bands, as the mean entropy of its columns in nats.

    A column holding a few lines scores low and one holding two sounds' lines at once scores
    higher; the floor rows contribute nothing.
    """
    magnitude = grid_magnitudes(grid)
    totals = magnitude.sum(axis=0, keepdims=True)
    share = magnitude / np.where(totals > 0.0, totals, 1.0)
    entropies = -(share * np.log(np.where(share > 0.0, share, 1.0))).sum(axis=0)
    return float(entropies.mean())


def _rises(values: tuple[float, ...]) -> bool:
    return bool(np.all(np.diff(values) >= 0.0))


def _falls(values: tuple[float, ...]) -> bool:
    return bool(np.all(np.diff(values) <= 0.0))
