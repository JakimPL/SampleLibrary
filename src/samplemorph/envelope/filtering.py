from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

from samplemorph.envelope.response import EnvelopeFilter, EnvelopeResponse, HeldEnd
from samplemorph.envelope.split import envelope_from_cepstrum
from samplemorph.geometry import LogFrequencyGeometry, analysis_taper


def filter_gain(envelope_filter: EnvelopeFilter, *, weight: float, bin_count: int) -> NDArray[np.float32]:
    """The gain a filter puts on every bin of every frame while the morph stands at `weight`.

    The coefficients draw the ratio between the two envelopes in the log domain, so scaling them by
    how far the path has travelled and reading them back over the bins gives the ratio raised to that
    distance. The end a filter holds reads a gain of one throughout.

    Shape: the result is ``(bin_count, frames)``.

    Raises:
        ValueError: the weight lies outside ``[0, 1]``.
    """
    return envelope_from_cepstrum(envelope_filter.coefficients * envelope_filter.travel_at(weight), bin_count=bin_count)


def filtered_waveform(
    transform: NDArray[np.complex128],
    envelope_filter: EnvelopeFilter,
    *,
    weight: float,
    geometry: LogFrequencyGeometry,
) -> NDArray[np.float64]:
    """The frames a sound makes audible once the filter has carried it `weight` of the way toward the other's envelope.

    The sound keeps the phase its own analysis measured, so the reading that inverts the transform is
    the one that analyzed it and the end a filter holds returns that sound itself. Shape: `transform`
    is ``(bins, frames)`` and belongs to the sound the filter holds.

    Raises:
        ValueError: the weight lies outside ``[0, 1]``.
    """
    gain = filter_gain(envelope_filter, weight=weight, bin_count=transform.shape[0])
    waveform: NDArray[np.float64] = librosa.istft(
        transform * gain,
        hop_length=geometry.hop_length,
        n_fft=geometry.fft_length,
        window=analysis_taper(geometry),
        length=envelope_filter.description.sample_count,
    )
    return waveform


def response_gain(response: EnvelopeResponse, *, held: HeldEnd, weight: float) -> NDArray[np.float32]:
    """The gain one end of a response takes at a weight, over the bins the response was read through."""
    return filter_gain(response.filter_held_to(held), weight=weight, bin_count=response.description.bin_count)
