from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.tracks import CENTS_PER_OCTAVE, PartialTracks


@dataclass(frozen=True)
class PartialPlaces:
    """Where each partial of a sound stands, how much of the sound it carries, and when it is heard.

    `cents` is the amplitude-weighted pitch a partial holds over its life and `share` the energy it
    carries of the sound's. `onset` and `offset` place its life on the stretch the sound sounds
    through, 0 at the first frame any partial sounds and 1 at the last, which reads two sounds of
    different lengths on one clock. Shapes: every array is ``(partials,)``.
    """

    cents: NDArray[np.float64]
    share: NDArray[np.float64]
    onset: NDArray[np.float64]
    offset: NDArray[np.float64]

    @property
    def count(self) -> int:
        return int(self.cents.shape[0])

    @property
    def loudness(self) -> NDArray[np.float64]:
        """How loud each partial stands, the root of the energy it carries."""
        loud: NDArray[np.float64] = np.sqrt(self.share)
        return loud

    @property
    def lifetime(self) -> NDArray[np.float64]:
        """How long each partial is heard, as a share of the stretch the whole sound sounds through."""
        heard: NDArray[np.float64] = self.offset - self.onset
        return heard

    @property
    def frequency_hz(self) -> NDArray[np.float64]:
        frequency: NDArray[np.float64] = 2.0 ** (self.cents / CENTS_PER_OCTAVE)
        return frequency


def partial_places(tracks: PartialTracks) -> PartialPlaces:
    """Each partial as one pitch, one share of the sound and one life, which is what a pairing reads it by."""
    energy = tracks.amplitude.astype(np.float64) ** 2
    weight = energy.sum(axis=1)
    total = float(weight.sum())
    cents = CENTS_PER_OCTAVE * np.log2(tracks.frequency_hz.astype(np.float64))
    onset, offset = _lives(tracks)
    return PartialPlaces(
        cents=np.where(weight > 0.0, (energy * cents).sum(axis=1) / np.where(weight > 0.0, weight, 1.0), cents[:, 0]),
        share=weight / total if total > 0.0 else np.zeros_like(weight),
        onset=onset,
        offset=offset,
    )


def _lives(tracks: PartialTracks) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Where each partial's life starts and ends on the stretch the whole sound sounds through."""
    sounding = tracks.sounding
    heard = sounding.any(axis=1)
    if not bool(heard.any()):
        silent = np.zeros(tracks.track_count, dtype=np.float64)
        return silent, silent.copy()

    first = np.where(heard, sounding.argmax(axis=1), 0)
    last = np.where(heard, tracks.frame_count - 1 - sounding[:, ::-1].argmax(axis=1), 0)
    start, end = int(first[heard].min()), int(last[heard].max())
    span = float(max(end - start, 1))
    return (first - start) / span, (last - start) / span
