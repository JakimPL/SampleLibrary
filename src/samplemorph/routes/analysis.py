from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.routes.route import HeardMono
from samplemorph.transport.analysis import TransportAnalysis, analyze
from samplemorph.transport.morph import TransportedSpectrogram
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import integrate_and_synthesize


class SpectralPath(Protocol):
    """A magnitude between two analyses at `weight`: the transport, or the blend it is judged against."""

    def __call__(
        self,
        first: TransportAnalysis,
        second: TransportAnalysis,
        *,
        weight: float,
        geometry: LogFrequencyGeometry,
        settings: TransportSettings,
    ) -> TransportedSpectrogram: ...


@dataclass(frozen=True)
class AnalysisRoute:
    """The route over the sounds' own Gaussian analyses: a spectral path between them, then phase gradient heap integration.

    Every point is heard at the fidelity of the analysis itself, the magnitude going straight to the
    phase integration, so two routes differing only in their path differ only in how they move
    between the ends.
    """

    path: SpectralPath
    geometry: LogFrequencyGeometry
    settings: TransportSettings

    def prepare(self, heard: HeardMono) -> TransportAnalysis:
        return analyze(heard.mono, rate_hz=heard.rate_hz, geometry=self.geometry, settings=self.settings)

    def render(self, first: TransportAnalysis, second: TransportAnalysis, *, weight: float) -> NDArray[np.float64]:
        spectrogram = self.path(first, second, weight=weight, geometry=self.geometry, settings=self.settings)
        return integrate_and_synthesize(
            spectrogram.magnitude, geometry=self.geometry, frame_count=spectrogram.sample_count
        )
