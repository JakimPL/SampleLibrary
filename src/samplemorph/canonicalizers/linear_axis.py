from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers import mel
from samplemorph.canonicalizers.common import bands_onto_linear_axis
from samplemorph.geometry import Geometry, MelGeometry


def onto_linear_axis(magnitude: NDArray[np.float64], *, geometry: Geometry) -> NDArray[np.float64]:
    """Read any axis's magnitude spectrogram onto the linear Fourier grid a vocoder inverts from.

    Every route back to audio passes through here, so what a vocoder meets while it is being taught
    is what it meets when it is asked to speak. The logarithmic axes place their bands by frequency
    and are read by interpolation; the mel axis carries its own filterbank and is read back through
    it.
    """
    if isinstance(geometry, MelGeometry):
        return mel.onto_linear_axis(magnitude, geometry=geometry)

    return bands_onto_linear_axis(
        magnitude,
        band_frequencies=geometry.band_frequencies,
        linear_frequencies=geometry.linear_frequencies,
    )
