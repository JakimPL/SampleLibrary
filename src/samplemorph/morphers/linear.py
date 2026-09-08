from __future__ import annotations

import numpy as np

from samplemorph.images import Conditioners, SampleLatent
from samplemorph.morphers import MorphWeights


class LinearMorpher:
    """Travels in a straight line between two latents, and separately between two conditioners.

    A straight line is what a codec trained to make intermediate points meaningful is expected to
    reward, so it is the reading every other route is measured against. The conditioners follow
    their own straight line, which places the result's pitch, length and level between the two
    samples' own -- and because they are already logarithms, a straight line between them is a
    geometric path in pitch, duration and gain, which is how each is heard.
    """

    def morph(self, first: SampleLatent, second: SampleLatent, *, weights: MorphWeights) -> SampleLatent:
        """Combine two latents at `weights`.

        Raises:
            ValueError: the two latents differ in length or describe different geometries, leaving
                no shared space for a straight line to run through.
        """
        if first.latent_size != second.latent_size:
            raise ValueError(
                f"a morph runs between latents of one size, got {first.latent_size} and {second.latent_size}"
            )
        if first.geometry != second.geometry:
            raise ValueError("a morph runs between latents describing one geometry")

        return SampleLatent(
            values=_between(first.values, second.values, weights.latent),
            conditioners=_between_conditioners(first.conditioners, second.conditioners, weights.conditioners),
            geometry=first.geometry,
        )


def _between(first: np.ndarray, second: np.ndarray, weight: float) -> np.ndarray:
    return first * (1.0 - weight) + second * weight


def _between_conditioners(first: Conditioners, second: Conditioners, weight: float) -> Conditioners:
    return Conditioners(
        translation_semitones=_scalar_between(first.translation_semitones, second.translation_semitones, weight),
        log_duration=_scalar_between(first.log_duration, second.log_duration, weight),
        log_gain=_scalar_between(first.log_gain, second.log_gain, weight),
    )


def _scalar_between(first: float, second: float, weight: float) -> float:
    return first * (1.0 - weight) + second * weight
