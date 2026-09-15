from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.modulation import (
    ModulationAxis,
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
    at 70 Hz) are signed modulation depths the lobe hears: a positive value is added warble or buzz,
    a negative value is micro-modulation the reconstruction has smoothed away, and a reconstruction
    that moves as its reference does reads zero on both, which is the target. A reading is heard
    once it clears the front end's `depth_floor`. `distance` is the unsigned, loudness-weighted
    deviation over every modulation bin of both lobes, so it bounds the size of either excess and
    reads a modulation that merely moved between bins. Every reading counts a channel and a moment
    by how loud the reference is there.
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
        loudness = loudness_weight(reference_read.level, floor=front_end.compressed_floor)
        excess[read.lobe.axis] = _weighted_lobe_depth(read, loudness=loudness) - _weighted_lobe_depth(
            reference_read, loudness=loudness
        )
        distance += float(
            (loudness[..., None] * reference_read.bin_weight * np.abs(read.depth - reference_read.depth)).sum()
        )
    return ModulationSpectrumDistance(
        fluctuation_excess=excess[ModulationAxis.FLUCTUATION],
        roughness_excess=excess[ModulationAxis.ROUGHNESS],
        distance=distance,
    )


@dataclass(frozen=True)
class ModulationLobeDepths:
    """The modulation depth one waveform carries on each lobe, every channel and moment counted by how loud it is."""

    fluctuation: float
    roughness: float


def modulation_lobe_depths(
    waveform: NDArray[np.float64], *, source_rate_hz: int = NOMINAL_WAV_RATE
) -> ModulationLobeDepths:
    """Read how deeply one waveform's envelopes fluctuate and roughen, at the rate it is heard at.

    Beside `modulation_spectrum_distance`, which holds a reconstruction against its reference, this
    reads a sound on its own, so a point between two sounds can be held against the depths of both.
    """
    front_end = design_modulation_front_end(sample_rate_hz=source_rate_hz)
    depths = {
        spectrum.lobe.axis: _weighted_lobe_depth(
            spectrum, loudness=loudness_weight(spectrum.level, floor=front_end.compressed_floor)
        )
        for spectrum in modulation_spectra(waveform, front_end=front_end)
    }
    return ModulationLobeDepths(
        fluctuation=depths[ModulationAxis.FLUCTUATION], roughness=depths[ModulationAxis.ROUGHNESS]
    )


def _weighted_lobe_depth(spectrum: ModulationSpectrum, *, loudness: NDArray[np.float64]) -> float:
    return float((loudness * spectrum.lobe_depth).sum())
