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

    The shape is read as the few coefficients that draw it and expanded back over the bins it came
    from. Shape: `magnitude` is ``(bins, frames)`` and so is the result.
    """
    return envelope_from_cepstrum(envelope_cepstrum(magnitude, settings=settings), bin_count=magnitude.shape[0])


def envelope_cepstrum(magnitude: NDArray[np.float32], *, settings: EnvelopeSettings) -> NDArray[np.float32]:
    """A magnitude's envelope as the coefficients that draw it, one set of them per frame.

    The loudness is read down to `floor_db` under the loudest bin of the whole sound, so a silent
    frame's envelope lies flat at the floor and the skirts between two harmonics count as part of
    the shape between them. Keeping the first `coefficient_count` coefficients of the loudness's
    cosine transform keeps every ripple slower than about two bins per coefficient across the
    spectrum, which is what a resonance is and a harmonic's lobe is not.

    The floor follows the loudest bin of the whole array, so a cepstrum describes the reading it was
    measured over, and two of them compare where they were read from one reading of one pair.

    Shape: `magnitude` is ``(bins, frames)``, the result ``(coefficient_count, frames)``.
    """
    peak = max(float(magnitude.max()), float(np.finfo(np.float32).tiny))
    floor = peak * 10.0 ** (-settings.floor_db / 20.0)
    loudness = np.log(np.maximum(magnitude, floor))
    coefficients: NDArray[np.float32] = dct(loudness, axis=0, norm="ortho")[: settings.coefficient_count]
    return coefficients


def envelope_from_cepstrum(coefficients: NDArray[np.float32], *, bin_count: int) -> NDArray[np.float32]:
    """The envelope a cepstrum draws, read back over `bin_count` bins.

    Shape: `coefficients` is ``(coefficient_count, frames)``, the result ``(bin_count, frames)``.
    """
    # The inverse transform at the full length reads the coefficients left out as zeros.
    envelope: NDArray[np.float32] = np.exp(idct(coefficients, n=bin_count, axis=0, norm="ortho")).astype(np.float32)
    return envelope
