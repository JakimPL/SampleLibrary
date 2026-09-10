from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.modulation import (
    ModulationAxis,
    ModulationFrontEnd,
    ModulationSpectrum,
    design_modulation_front_end,
    modulation_spectra,
)
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.measurement.weighting import loudness_weight


@dataclass(frozen=True)
class ModulationSpectrumDistance:
    """Three readings of the modulation a reconstruction carries against its reference, on the two
    axes a listener hears a phase gargle on.

    `fluctuation_excess` (1 to 20 Hz, peaking at 4 Hz) and `roughness_excess` (20 to 150 Hz, peaking
    at 70 Hz) are signed modulation depths: a positive value is added warble or buzz, a negative
    value is micro-modulation the reconstruction has smoothed away, and a reconstruction that moves
    as its reference does reads zero on both, which is the target. `distance` is the unsigned,
    loudness-weighted deviation over every modulation bin of both lobes, so it bounds the size of
    either excess. Every reading counts a channel and a moment by how loud the reference is there.
    """

    fluctuation_excess: float
    roughness_excess: float
    distance: float


def modulation_spectrum_distance(
    reconstruction: NDArray[np.float64],
    reference: NDArray[np.float64],
    *,
    source_rate_hz: int = NOMINAL_WAV_RATE,
) -> ModulationSpectrumDistance:
    """Read how a reconstruction's envelope modulation departs from its reference's.

    Both waveforms are read at `source_rate_hz`, the rate the samples are heard at, since the
    modulation rate a comb produces scales with playback rate and the lobes are placed in heard
    hertz; the store's nominal rate is the default because that is the rate every stored object and
    vocoder output carries. The shorter length is the one compared, and the envelopes come from the
    time-domain waveform through the front end's filterbank, which is what reaches the roughness
    lobe a frame-rate reading falls short of.
    """
    length = min(reconstruction.shape[0], reference.shape[0])
    front_end = design_modulation_front_end(sample_rate_hz=source_rate_hz)
    reconstruction_spectra = modulation_spectra(reconstruction[:length], front_end=front_end)
    reference_spectra = modulation_spectra(reference[:length], front_end=front_end)
    excess: dict[ModulationAxis, float] = {}
    distance = 0.0
    for read, reference_read in zip(reconstruction_spectra, reference_spectra, strict=True):
        weight = _cell_weight(reference_read, front_end=front_end)
        difference = read.depth - reference_read.depth
        excess[read.lobe.axis] = float((weight * difference).sum())
        distance += float((weight * np.abs(difference)).sum())
    return ModulationSpectrumDistance(
        fluctuation_excess=excess[ModulationAxis.FLUCTUATION],
        roughness_excess=excess[ModulationAxis.ROUGHNESS],
        distance=distance,
    )


def _cell_weight(reference_read: ModulationSpectrum, *, front_end: ModulationFrontEnd) -> NDArray[np.float64]:
    """How much each channel, frame and bin counts: the reference's loudness there times the bin's share of the lobe."""
    loudness = loudness_weight(reference_read.level, floor=front_end.compressed_floor)
    weight: NDArray[np.float64] = loudness[..., None] * reference_read.bin_weight
    return weight
