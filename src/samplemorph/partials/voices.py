from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks


@dataclass(frozen=True)
class PartialVoices:
    """Where each partial of a sound sits and how much of the sound it carries.

    `cents` is the amplitude-weighted pitch a partial holds over its life, and `share` its energy
    over the sound's. Shapes: both arrays are ``(partials,)``.
    """

    cents: NDArray[np.float64]
    share: NDArray[np.float64]

    @property
    def count(self) -> int:
        return int(self.cents.shape[0])

    @property
    def loudness(self) -> NDArray[np.float64]:
        """How loud each partial stands, the root of the energy it carries."""
        loud: NDArray[np.float64] = np.sqrt(self.share)
        return loud

    @property
    def frequency_hz(self) -> NDArray[np.float64]:
        frequency: NDArray[np.float64] = 2.0 ** (self.cents / CENTS_PER_OCTAVE)
        return frequency


def partial_voices(tracks: PartialTracks) -> PartialVoices:
    """Each partial as one pitch and one share of the sound, which is what a pairing reads it by."""
    energy = tracks.amplitude.astype(np.float64) ** 2
    weight = energy.sum(axis=1)
    total = float(weight.sum())
    cents = CENTS_PER_OCTAVE * np.log2(tracks.frequency_hz.astype(np.float64))
    return PartialVoices(
        cents=np.where(weight > 0.0, (energy * cents).sum(axis=1) / np.where(weight > 0.0, weight, 1.0), cents[:, 0]),
        share=weight / total if total > 0.0 else np.zeros_like(weight),
    )
