from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from samplemorph.partials.settings import FateSettings
from samplemorph.partials.tracks import PartialTracks


def fate_groups(tracks: PartialTracks, *, settings: FateSettings) -> NDArray[np.intp]:
    """Which object each channel of a sound belongs to, channels that rise and fall together in one.

    Two partials of one struck string swell and decay as one, and two sounds struck apart do not, so
    the shape a channel's loudness draws over the whole sound says what it belongs to. Reading a
    sound this way binds a harmonic series together on evidence that holds for a bell and a cymbal
    too, since it asks nothing about whole multiples. Shape: the result is ``(channels,)``.
    """
    if tracks.track_count == 0:
        return np.zeros(0, dtype=np.intp)
    if tracks.track_count == 1:
        return np.zeros(1, dtype=np.intp)

    shape = _loudness_shape(tracks, settings=settings)
    agreement = np.clip(shape @ shape.T, -1.0, 1.0)
    apart = squareform(np.clip(1.0 - agreement, 0.0, 2.0), checks=False)
    together = fcluster(linkage(apart, method="average"), t=1.0 - settings.together, criterion="distance")
    grouped: NDArray[np.intp] = np.asarray(together, dtype=np.intp) - 1
    return grouped


def _loudness_shape(tracks: PartialTracks, *, settings: FateSettings) -> NDArray[np.float64]:
    """The shape each channel's loudness draws over the sound, level and length taken out of it.

    Shape: the result is ``(channels, frames)``, each row centered on its own mean and scaled to unit
    length, so a row against another reads as the agreement between the two shapes.
    """
    amplitude = tracks.amplitude.astype(np.float64)
    peak = np.maximum(amplitude.max(axis=1, keepdims=True), np.finfo(np.float64).tiny)
    floor = peak * 10.0 ** (-settings.silent_shape_db / 20.0)
    loud = np.log(np.maximum(amplitude, floor))
    centered = loud - loud.mean(axis=1, keepdims=True)
    length = np.sqrt((centered**2).sum(axis=1, keepdims=True))
    return np.where(length > 0.0, centered / np.where(length > 0.0, length, 1.0), 0.0)
