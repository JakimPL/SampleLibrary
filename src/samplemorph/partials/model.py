from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.geometry import LogFrequencyGeometry, gaussian_taper
from samplemorph.partials.channels import Channels, channelize
from samplemorph.partials.peaks import SILENT_MAGNITUDE, analysis_length, gaussian_transform, pick_peaks
from samplemorph.partials.residual import residual_energy
from samplemorph.partials.settings import PartialSettings
from samplemorph.partials.tracks import PartialTracks, track_peaks
from samplemorph.transport.analysis import TransportAnalysis, analysis_from_energy, analyze
from samplemorph.transport.settings import TransportSettings


@dataclass(frozen=True)
class SinusoidalModel:
    """One sound read as the lines it sounds along over a residual, beside the whole sound they came from.

    `channels` are the notes' harmonics and the partials standing free of them, each an oscillator's
    worth of frequency and amplitude over time; `residual` is what the spectrum holds beyond them, the
    noise, the attacks and the clusters too close to resolve; `whole` is the sound's own analysis,
    which is what two sounds are aligned in time by. A sound with no partial to track keeps its whole
    analysis as its residual, which leaves it to travel exactly as a transport carries it.
    """

    channels: Channels
    whole: TransportAnalysis
    residual: TransportAnalysis
    rate_hz: float

    @property
    def nbytes(self) -> int:
        return int(
            self.channels.tracks.frequency_hz.nbytes
            + self.channels.tracks.amplitude.nbytes
            + self.whole.nbytes
            + self.residual.nbytes
        )


def analyze_model(
    mono: PreparedMono,
    *,
    rate_hz: float,
    geometry: LogFrequencyGeometry,
    transport_settings: TransportSettings,
    partial_settings: PartialSettings,
) -> SinusoidalModel:
    """Read a prepared waveform heard at `rate_hz` as partials over a residual.

    The partials are followed on a window long enough to tell neighboring partials apart, and each
    one's amplitude is held to the quieter of that reading and the shorter analysis the residual
    lives on, so a partial rises no sooner than the sound itself does. What their lobes explain of
    the spectrum comes off the residual, read where each partial was measured, and the partials are
    then read as notes, which puts every harmonic of a note on its own fundamental. Both analyses
    step by the geometry's hop, which puts every partial's frame beside the spectrum's own.
    """
    whole = analyze(mono, rate_hz=rate_hz, geometry=geometry, settings=transport_settings)
    partials = _sounded_partials(
        mono, energy=whole.energy, rate_hz=rate_hz, geometry=geometry, settings=partial_settings
    )
    channels = channelize(partials, settings=partial_settings)
    return SinusoidalModel(
        channels=channels,
        whole=whole,
        residual=analysis_from_energy(
            residual_energy(whole.energy, tracks=partials, fft_length=geometry.fft_length, settings=partial_settings),
            onset_sample=whole.onset_sample,
            sample_count=whole.sample_count,
            settings=transport_settings,
        ),
        rate_hz=rate_hz,
    )


def _sounded_partials(
    mono: PreparedMono,
    *,
    energy: NDArray[np.float32],
    rate_hz: float,
    geometry: LogFrequencyGeometry,
    settings: PartialSettings,
) -> PartialTracks:
    window_length = analysis_length(rate_hz, settings=settings)
    peaks = pick_peaks(
        gaussian_transform(mono, window_length=window_length, hop_length=geometry.hop_length),
        rate_hz=rate_hz,
        window_length=window_length,
        settings=settings,
    )
    tracks = track_peaks(peaks, hop_length=geometry.hop_length, rate_hz=rate_hz, settings=settings)
    if tracks.track_count == 0:
        return tracks
    return PartialTracks(
        frequency_hz=tracks.frequency_hz,
        amplitude=np.minimum(tracks.amplitude, _short_reading(tracks, energy=energy, fft_length=geometry.fft_length)),
        hop_length=tracks.hop_length,
        rate_hz=tracks.rate_hz,
    )


def _short_reading(tracks: PartialTracks, *, energy: NDArray[np.float32], fft_length: int) -> NDArray[np.float32]:
    """Each partial's amplitude as the shorter analysis reads it, through the parabola over its three nearest bins.

    Shape: the result is ``(tracks, frames)``.
    """
    centers = tracks.frequency_hz.astype(np.float64) * fft_length / tracks.rate_hz
    nearest = np.clip(np.rint(centers).astype(np.int64), 1, energy.shape[0] - 2)
    frames = np.broadcast_to(np.arange(tracks.frame_count), centers.shape)
    logarithm = np.log(np.maximum(energy, SILENT_MAGNITUDE).astype(np.float64))
    below, center, above = (logarithm[nearest + offset, frames] for offset in (-1, 0, 1))
    curvature = 0.5 * (below - 2.0 * center + above)
    slope = 0.5 * (above - below)
    # A lobe peaks within half a bin of its nearest one, so the vertex is read no further out than one.
    offset = np.clip(-slope / (2.0 * np.where(curvature < 0.0, curvature, -1.0)), -1.0, 1.0)
    vertex = center + slope * offset + curvature * offset**2
    amplitude: NDArray[np.float32] = (2.0 * np.exp(vertex / 2.0) / float(gaussian_taper(fft_length).sum())).astype(
        np.float32
    )
    return amplitude
