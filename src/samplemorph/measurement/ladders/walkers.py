from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import shift_bands
from samplemorph.measurement.ladders.truth import Ladder, UnrelatedPair

CROSSFADE_WALKER_NAME: Final[str] = "crossfade"
ORACLE_WALKER_NAME: Final[str] = "oracle"


class GridAutoencoder(Protocol):
    """Reads a batch of pooled grids as latent vectors, and decodes latent vectors back into grids.

    Shapes: grids are ``(count, bands, columns)`` and latents ``(count, latent size)``.
    """

    def encode(self, grids: NDArray[np.float32]) -> NDArray[np.float32]: ...

    def decode(self, latents: NDArray[np.float32]) -> NDArray[np.float32]: ...


@dataclass(frozen=True)
class Walk:
    """What one walker made of a ladder: its reading of every true step, and its own path between the ends.

    A walker is judged against its own readings of the truth, so whatever it loses in
    reconstructing a sound at all cancels, and what remains is how its path runs between the ends.
    Shapes: `reconstructions` is ``(true steps, bands, columns)`` and `path` ``(steps, bands, columns)``.
    """

    reconstructions: NDArray[np.float32]
    path: NDArray[np.float32]


class LadderWalker(Protocol):
    """A way from one end of a ladder to the other, read against the ladder's truth.

    `walk` returns nothing for a ladder the walker has no path for, as a translation has none for a
    ladder whose truth is not a translation.
    """

    @property
    def name(self) -> str: ...

    def walk(self, ladder: Ladder) -> Walk | None: ...

    def walk_pair(self, pair: UnrelatedPair) -> Walk | None: ...


class CrossfadeWalker:
    """The decibel crossfade of the two ends, the path a model whose straight lines only dissolve takes."""

    @property
    def name(self) -> str:
        return CROSSFADE_WALKER_NAME

    def walk(self, ladder: Ladder) -> Walk:
        return Walk(
            reconstructions=ladder.truth, path=crossfade(ladder.truth[0], ladder.truth[-1], weights=ladder.weights)
        )

    def walk_pair(self, pair: UnrelatedPair) -> Walk:
        return Walk(reconstructions=pair.ends, path=crossfade(pair.ends[0], pair.ends[1], weights=pair.weights))


@dataclass(frozen=True)
class TranslationOracle:
    """The first end moved along the band axis by the weight's share of the interval, the path a mover takes.

    On a retuning the truth is such a move, less what the analysis window and the Nyquist frequency
    add, so the oracle shows what a move reads as. A step between whole bands is drawn by
    interpolating neighboring bands, which on a pooled axis stands a few decibels from the truth,
    so the oracle is a mover the readings place nearest the truth rather than at it.
    """

    bands_per_semitone: int

    @property
    def name(self) -> str:
        return ORACLE_WALKER_NAME

    def walk(self, ladder: Ladder) -> Walk | None:
        if not ladder.is_translation:
            return None
        first = ladder.truth[0].astype(np.float64)
        path = np.stack(
            [
                shift_bands(first, weight * ladder.interval_semitones * self.bands_per_semitone)
                for weight in ladder.weights
            ]
        ).astype(np.float32)
        return Walk(reconstructions=ladder.truth, path=path)

    def walk_pair(self, pair: UnrelatedPair) -> None:  # pylint: disable=unused-argument
        return None


class LatentWalker:
    """The straight line between two ends' latent vectors, decoded step by step."""

    def __init__(self, *, name: str, autoencoder: GridAutoencoder) -> None:
        self._name = name
        self._autoencoder = autoencoder

    @property
    def name(self) -> str:
        return self._name

    def walk(self, ladder: Ladder) -> Walk:
        return self._walked(ladder.truth, weights=ladder.weights)

    def walk_pair(self, pair: UnrelatedPair) -> Walk:
        return self._walked(pair.ends, weights=pair.weights)

    def _walked(self, grids: NDArray[np.float32], *, weights: tuple[float, ...]) -> Walk:
        """Every grid read back through the latent space, and the decoded line between the first's latent and the last's."""
        latents = self._autoencoder.encode(grids)
        shares = np.asarray(weights, dtype=np.float32)[:, None]
        line = (1.0 - shares) * latents[:1] + shares * latents[-1:]
        return Walk(reconstructions=self._autoencoder.decode(latents), path=self._autoencoder.decode(line))


def crossfade(
    first: NDArray[np.float32], second: NDArray[np.float32], *, weights: tuple[float, ...]
) -> NDArray[np.float32]:
    """Two grids crossfaded at every weight, which on a decibel grid is a crossfade in decibels.

    Shape: ``(steps, bands, columns)``.
    """
    shares = np.asarray(weights, dtype=np.float32)[:, None, None]
    return (1.0 - shares) * first[None] + shares * second[None]
