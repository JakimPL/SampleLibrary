from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.fft import dct, idct

from samplemorph.envelope.settings import EnvelopeSettings


@dataclass(frozen=True)
class SplitSpectrum:
    """A magnitude as the smooth envelope it stands in and the excitation under it, whose product is the magnitude again.

    Shapes: both arrays are ``(bins, frames)``.
    """

    envelope: NDArray[np.float32]
    excitation: NDArray[np.float32]


def split_spectrum(magnitude: NDArray[np.float32], *, settings: EnvelopeSettings) -> SplitSpectrum:
    """Read a magnitude as its envelope and what sounds under it: harmonics, noise and silence alike."""
    envelope = spectral_envelope(magnitude, settings=settings)
    return SplitSpectrum(envelope=envelope, excitation=(magnitude / envelope).astype(np.float32))


def spectral_envelope(magnitude: NDArray[np.float32], *, settings: EnvelopeSettings) -> NDArray[np.float32]:
    """The smooth shape a magnitude stands in: its loudness over frequency, drawn by its slowest cosines alone.

    The loudness is read down to `floor_db` under the loudest bin of the whole sound, so a silent
    frame's envelope lies flat at the floor and the skirts between two harmonics count as part of
    the shape between them. Keeping the first `coefficient_count` coefficients of the loudness's
    cosine transform keeps every ripple slower than about two bins per coefficient across the
    spectrum, which is what a resonance is and a harmonic's lobe is not. Shape: `magnitude` is
    ``(bins, frames)`` and so is the result.
    """
    peak = max(float(magnitude.max()), float(np.finfo(np.float32).tiny))
    floor = peak * 10.0 ** (-settings.floor_db / 20.0)
    loudness = np.log(np.maximum(magnitude, floor))
    slowest = dct(loudness, axis=0, norm="ortho")[: settings.coefficient_count]
    # The inverse transform at the full length reads the coefficients left out as zeros.
    envelope: NDArray[np.float32] = np.exp(idct(slowest, n=magnitude.shape[0], axis=0, norm="ortho")).astype(np.float32)
    return envelope
