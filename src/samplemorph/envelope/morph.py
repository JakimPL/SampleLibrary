from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.envelope.split import SplitSpectrum, split_spectrum
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.frame_reading import read_frames
from samplemorph.transport.morph import FIRST_END_WEIGHT, SECOND_END_WEIGHT, TransportedSpectrogram, heard_as_analyzed
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import build_time_map


@dataclass(frozen=True)
class EnvelopePath:
    """The spectral path that moves the envelope between two sounds and keeps one sound's excitation whole under it.

    Both sounds are aligned in time by the transport's own map and read along it, and each read
    frame is split into the smooth envelope it stands in and the excitation under it. The path's
    envelope lies at `weight` between the two in decibels, bin by bin, so resonances, brightness and
    the balance of registers move from one sound's to the other's. Under it sounds one sound's
    excitation whole: the first's at every weight below the settings' switch weight, the second's
    from it on. A sound's harmonics therefore travel as one series at one pitch, a chord stays the
    chord it was, and the pitch content changes hands at a single point of the path. The ends are
    each sound's own analysis.
    """

    envelope_settings: EnvelopeSettings

    def __call__(
        self,
        first: TransportAnalysis,
        second: TransportAnalysis,
        *,
        weight: float,
        geometry: LogFrequencyGeometry,
        settings: TransportSettings,
    ) -> TransportedSpectrogram:
        """The magnitude `weight` of the way from one sound to another, one excitation under the envelope between them.

        Raises:
            ValueError: the weight lies outside ``[0, 1]``.
        """
        if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
            raise ValueError(f"an envelope morph runs between weights 0 and 1, got {weight}")
        if weight == FIRST_END_WEIGHT:
            return heard_as_analyzed(first)
        if weight == SECOND_END_WEIGHT:
            return heard_as_analyzed(second)

        time_map = build_time_map(first, second, weight=weight, hop_length=geometry.hop_length, settings=settings)
        first_split = self._split_along(
            first, positions=time_map.first_positions, rates=time_map.first_rates, settings=settings
        )
        second_split = self._split_along(
            second, positions=time_map.second_positions, rates=time_map.second_rates, settings=settings
        )
        excitation = (
            second_split.excitation if weight >= self.envelope_settings.switch_weight else first_split.excitation
        )
        magnitude = _between(first_split.envelope, second_split.envelope, weight=weight) * excitation
        return TransportedSpectrogram(magnitude=magnitude.astype(np.float32), sample_count=time_map.sample_count)

    def _split_along(
        self,
        analysis: TransportAnalysis,
        *,
        positions: NDArray[np.float64],
        rates: NDArray[np.float64],
        settings: TransportSettings,
    ) -> SplitSpectrum:
        """A sound read where a time map points, split into its envelope and its excitation."""
        energy = read_frames(
            analysis.energy, positions=positions, rates=rates, maximum_half_width=settings.maximum_reading_half_width
        )
        return split_spectrum(np.sqrt(np.maximum(energy, 0.0)).astype(np.float32), settings=self.envelope_settings)


def _between(first: NDArray[np.float32], second: NDArray[np.float32], *, weight: float) -> NDArray[np.float32]:
    """The envelope `weight` of the way from one to another, bin by bin in decibels."""
    between: NDArray[np.float32] = first ** (1.0 - weight) * second**weight
    return between
