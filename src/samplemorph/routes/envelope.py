from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.coordinates.readers import PitchReading, SubharmonicReader
from samplemorph.envelope.glide import PitchedAnalysis
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.routes.route import HeardMono
from samplemorph.transport.analysis import TransportAnalysis, analyze
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import integrate_and_synthesize


@dataclass(frozen=True)
class PreparedPair:
    """Two ends read once by a route, ready to render any weight between them, and the bytes the two hold."""

    route: EnvelopeRoute
    first: PitchedAnalysis
    second: PitchedAnalysis

    @property
    def nbytes(self) -> int:
        return self.first.nbytes + self.second.nbytes

    def render(self, *, weight: float) -> NDArray[np.float64]:
        return self.route.render(self.first, self.second, weight=weight)


@dataclass(frozen=True)
class EnvelopeRoute:
    """The route every morph takes: the envelope moves between two sounds' own Gaussian analyses under an excitation, then phase gradient heap integration makes the magnitude audible.

    Every point is heard at the fidelity of the analysis itself. With a `reader`, each end is read
    for its pitch once, as it is prepared, in the frame the pair is heard in, and the kept excitation
    glides from one end's pitch to the other's; a reading the reader trusts less than its own
    `trusted_reliability` counts as no pitch, and a pair with an end of no pitch renders with the
    excitation at its own pitch. Without a `reader`, every excitation holds its own pitch.
    """

    path: EnvelopePath
    reader: SubharmonicReader | None
    geometry: LogFrequencyGeometry
    settings: TransportSettings

    def analyze(self, heard: HeardMono) -> TransportAnalysis:
        """One end's Gaussian analysis, which is what a filter between two ends is read from."""
        return analyze(heard.mono, rate_hz=heard.rate_hz, geometry=self.geometry)

    def prepare(self, heard: HeardMono) -> PitchedAnalysis:
        return PitchedAnalysis(analysis=self.analyze(heard), pitch_semitones=self._trusted_pitch(heard.mono))

    def prepare_pair(self, first: HeardMono, second: HeardMono) -> PreparedPair:
        return PreparedPair(route=self, first=self.prepare(first), second=self.prepare(second))

    def render(self, first: PitchedAnalysis, second: PitchedAnalysis, *, weight: float) -> NDArray[np.float64]:
        spectrogram = self.path.gliding(first, second, weight=weight, geometry=self.geometry, settings=self.settings)
        return integrate_and_synthesize(
            spectrogram.magnitude, geometry=self.geometry, frame_count=spectrogram.sample_count
        )

    def _trusted_pitch(self, mono: PreparedMono) -> float | None:
        if self.reader is None:
            return None
        return _trusted(self.reader.read(mono), trusted_reliability=self.reader.trusted_reliability)


def _trusted(reading: PitchReading | None, *, trusted_reliability: float) -> float | None:
    """A reading's pitch when its reader trusts it at least `trusted_reliability`, and None otherwise."""
    if reading is None or reading.reliability < trusted_reliability:
        return None
    return reading.semitones
