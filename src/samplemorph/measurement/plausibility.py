from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from samplemorph.codecs import SampleCodec
from samplemorph.images import SampleLatent
from samplemorph.measurement.comparison import grid_distance
from samplemorph.morphers import Morpher, MorphWeights

DEFAULT_MORPH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class MorphEndpoint:
    """One end of a morph: the sample it starts or arrives at, and that sample's own latent."""

    sample_hash: str
    latent: SampleLatent


@dataclass(frozen=True)
class MorphStep:
    """One point along a morph, and how far its decoded grid sits from each endpoint."""

    weight: float
    distance_to_first: float
    distance_to_second: float


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
    steps = []
    for weight in weights:
        morphed = morpher.morph(first.latent, second.latent, weights=MorphWeights.uniform(weight))
        decoded = codec.decode(morphed).grid
        steps.append(
            MorphStep(
                weight=weight,
                distance_to_first=grid_distance(decoded, first_grid),
                distance_to_second=grid_distance(decoded, second_grid),
            )
        )
    return MorphPlausibility(first_hash=first.sample_hash, second_hash=second.sample_hash, steps=tuple(steps))


def _rises(values: tuple[float, ...]) -> bool:
    return bool(np.all(np.diff(values) >= 0.0))


def _falls(values: tuple[float, ...]) -> bool:
    return bool(np.all(np.diff(values) <= 0.0))
