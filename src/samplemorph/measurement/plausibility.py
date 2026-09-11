from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import fundamental_band, restore_columns, to_normalized_decibels
from samplemorph.codecs import SampleCodec
from samplemorph.geometry import REFERENCE_FREQUENCY_HZ, SEMITONES_PER_OCTAVE
from samplemorph.images import SampleLatent, SoundImage
from samplemorph.measurement.comparison import grid_distance
from samplemorph.morphers import Morpher, MorphWeights

DEFAULT_MORPH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)
# The grid spans this many decibels between its floor and its peak, which is what turns a cell
# back into a magnitude a spread can be read from.
GRID_DYNAMIC_RANGE_DB: Final[float] = 100.0
# The lowest frequency a pitch is read at: an axis whose first band sits at zero hertz reads there
# as this, which keeps the reading finite where nothing audible is pitched.
PITCH_FLOOR_HZ: Final[float] = 20.0


@dataclass(frozen=True)
class MorphEndpoint:
    """One end of a morph: the sample it starts or arrives at, and that sample's own latent."""

    sample_hash: str
    latent: SampleLatent


@dataclass(frozen=True)
class MorphStep:
    """One point along a morph: how far its decoded grid sits from each endpoint, and what kind of sound it is.

    Four readings guard against the ways a path can fail to be a sound between two others.
    `spread_excess` is the step's spectral spread over the larger of the two endpoints' own: two
    sounds played at once carry both patterns and spread wider than either. `energy_share` is the
    step's energy over the mean of the endpoints': a straight line through a grid of decibels thins
    out whatever the two sounds do not share, so a step carrying a fraction of the energy is the
    shadow of both rather than a sound between them. `pitch_deviation_semitones` is how far the
    step's pitch sits from the line between the endpoints' pitches: a morph between two notes
    glides from one to the other, and a step off that line plays a note neither endpoint asked for.
    `blend_distance` is how far the step's grid sits from the crossfade of the two endpoint grids
    at this weight, over the endpoints' own distance: a codec that has learned to blend its inputs
    reads zero here at every step, and a morph that states a sound of its own reads above it.
    A sound holds its energy, spreads no wider, keeps its pitch on the line, and is more than the
    average of its endpoints.
    """

    weight: float
    distance_to_first: float
    distance_to_second: float
    spread_excess: float
    energy_share: float
    pitch_deviation_semitones: float
    blend_distance: float


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
    def largest_pitch_deviation(self) -> float:
        """How far off the line between the endpoints' pitches the path strays, at its worst step.

        Read the way the alignment reads a fundamental, so it says what a listener hears of the
        path's pitch on a pair that has one; a pair of unpitched sounds gets a reading too, of
        wherever their energy sits lowest, which says nothing about them.
        """
        return max(abs(step.pitch_deviation_semitones) for step in self.steps)

    @property
    def smallest_blend_distance(self) -> float:
        """How close to a plain crossfade of the endpoints the path comes, at its most blended interior step.

        The endpoints themselves are their own crossfade, so only the steps between them are
        read; a path with no interior step reads zero, since nothing about it tells it from a
        crossfade.
        """
        interior = tuple(step.blend_distance for step in self.steps if 0.0 < step.weight < 1.0)
        return min(interior) if interior else 0.0

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

    first_image = codec.decode(first.latent)
    second_image = codec.decode(second.latent)
    first_grid = first_image.grid
    second_grid = second_image.grid
    endpoint_spread = max(spectral_spread(first_grid), spectral_spread(second_grid))
    endpoint_energy = 0.5 * (grid_energy(first_grid) + grid_energy(second_grid))
    endpoint_distance = grid_distance(first_grid, second_grid)
    first_pitch = heard_pitch_semitones(first_image)
    second_pitch = heard_pitch_semitones(second_image)
    steps = []
    for weight in weights:
        morphed = morpher.morph(first.latent, second.latent, weights=MorphWeights.uniform(weight))
        image = codec.decode(morphed)
        decoded = image.grid
        steps.append(
            MorphStep(
                weight=weight,
                distance_to_first=grid_distance(decoded, first_grid),
                distance_to_second=grid_distance(decoded, second_grid),
                spread_excess=spectral_spread(decoded) - endpoint_spread,
                energy_share=grid_energy(decoded) / endpoint_energy if endpoint_energy > 0.0 else 0.0,
                pitch_deviation_semitones=heard_pitch_semitones(image)
                - ((1.0 - weight) * first_pitch + weight * second_pitch),
                blend_distance=blend_distance(
                    decoded, first=first_grid, second=second_grid, weight=weight, endpoint_distance=endpoint_distance
                ),
            )
        )
    return MorphPlausibility(first_hash=first.sample_hash, second_hash=second.sample_hash, steps=tuple(steps))


def blend_distance(
    decoded: NDArray[np.float64],
    *,
    first: NDArray[np.float64],
    second: NDArray[np.float64],
    weight: float,
    endpoint_distance: float,
) -> float:
    """How far a decoded grid sits from the crossfade of the two endpoint grids at `weight`, over their own distance.

    Identical endpoints have no crossfade to be told from, so the reading is zero there.
    """
    if endpoint_distance <= 0.0:
        return 0.0
    crossfade = (1.0 - weight) * first + weight * second
    return grid_distance(decoded, crossfade) / endpoint_distance


def heard_pitch_semitones(image: SoundImage) -> float:
    """Where an image's harmonic series is built, in semitones from the reference frequency, as it is heard.

    The reading is taken on the analysis grid restored from the image, so the alignment's
    translation is back in it and the pitch is the one a vocoder hands on. The playback rate a
    rendered file is written at multiplies every step of one morph by a factor that moves in a
    straight line with the weight, so a path measured here and the heard one differ by a line and
    a deviation from the line is the same in both. The series is found the way the alignment finds
    a fundamental (`fundamental_band`), which is what makes a morph on that anchor accountable to
    this reading.
    """
    columns = restore_columns(image.grid, geometry=image.geometry, conditioners=image.conditioners)
    normalized, _ = to_normalized_decibels(columns, dynamic_range_db=image.geometry.dynamic_range_db)
    band = fundamental_band(normalized, geometry=image.geometry)
    frequency = max(float(image.geometry.band_frequencies[band]), PITCH_FLOOR_HZ)
    return SEMITONES_PER_OCTAVE * float(np.log2(frequency / REFERENCE_FREQUENCY_HZ))


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
