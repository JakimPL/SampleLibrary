from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class Standardization:
    """The center and scale one body of feature vectors was read onto.

    Carrying the two lets a vector extracted later land in the same space the body defines, which is
    what a retrieval query needs: a descriptor taken from a retuned waveform is only comparable to
    the catalog's own vectors when both were read on one scale.
    """

    center: NDArray[np.float64]
    scale: NDArray[np.float64]

    def apply(self, feature_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
        """Read further vectors onto the scale this standardization already fixed."""
        standardized: NDArray[np.float64] = (feature_matrix - self.center) / self.scale
        return standardized


def fit_standardization(feature_matrix: NDArray[np.float64]) -> Standardization:
    """Measure the center and scale of one body of feature vectors.

    Extractors mix quantities carrying their own units: a centroid in hertz, a coefficient around
    zero, a fraction inside ``[0, 1]``. A distance over the raw mixture is decided by whichever
    feature spans the widest numbers, so it measures a unit choice. Reading every feature on one
    scale makes a distance describe the sample instead.

    Features that hold one value throughout keep a scale of one, so they contribute nothing to a
    distance and leave every other feature's contribution intact.
    """
    scaler = StandardScaler().fit(feature_matrix)
    scale = np.asarray(scaler.scale_, dtype=np.float64)
    return Standardization(center=np.asarray(scaler.mean_, dtype=np.float64), scale=np.where(scale > 0.0, scale, 1.0))


def standardize(feature_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Center each feature on zero and scale it to unit variance across the body given.

    The projection a promoted cloud is fitted from and the harness that scores a descriptor share
    this one definition, so a distance means the same thing in both.
    """
    return fit_standardization(feature_matrix).apply(feature_matrix)
