from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import log_frequency, mel
from samplemorph.canonicalizers.common import bands_onto_linear_axis
from samplemorph.geometry import ConstantQGeometry, Geometry, LogFrequencyGeometry, MelGeometry


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: Geometry) -> NDArray[np.float64]:
    """Read any axis's magnitude spectrogram onto the linear Fourier grid a vocoder inverts from.

    Every route back to audio passes through here, so what a vocoder meets while it is being taught
    is what it meets when it is asked to speak. Each axis is read back the way it was read in: the
    mel axis through its own filterbank, the log-frequency axis by the least-squares inverse of its
    band averaging, and the constant-Q axis by interpolation between its band centers.
    """
    match geometry:
        case MelGeometry():
            return mel.onto_linear_axis(magnitude, geometry=geometry)
        case LogFrequencyGeometry():
            return log_frequency.onto_linear_axis(magnitude, geometry=geometry)
        case ConstantQGeometry():
            return bands_onto_linear_axis(
                magnitude,
                band_frequencies=geometry.band_frequencies,
                linear_frequencies=geometry.linear_frequencies,
            )
