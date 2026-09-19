from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.coordinates.readers import PitchReader, PitchReading
from samplemorph.envelope.glide import PitchedAnalysis
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.routes.route import HeardMono
from samplemorph.transport.analysis import analyze
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import integrate_and_synthesize


@dataclass(frozen=True)
class GlidingRoute:
    """The envelope route whose kept excitation glides from one end's pitch to the other's, both read by `reader`.

    Each end is analyzed as the envelope route analyzes it and read for its pitch once, as it is
    prepared, in the frame the pair is heard in; a reading the reader trusts less than its own
    `trusted_reliability` counts as no pitch, and a pair with an end of no pitch renders as the
    envelope route does.
    """

    path: EnvelopePath
    reader: PitchReader
    geometry: LogFrequencyGeometry
    settings: TransportSettings

    def prepare(self, heard: HeardMono) -> PitchedAnalysis:
        return PitchedAnalysis(
            analysis=analyze(heard.mono, rate_hz=heard.rate_hz, geometry=self.geometry, settings=self.settings),
            pitch_semitones=self._trusted_pitch(heard.mono),
        )

    def render(self, first: PitchedAnalysis, second: PitchedAnalysis, *, weight: float) -> NDArray[np.float64]:
        spectrogram = self.path.gliding(first, second, weight=weight, geometry=self.geometry, settings=self.settings)
        return integrate_and_synthesize(
            spectrogram.magnitude, geometry=self.geometry, frame_count=spectrogram.sample_count
        )

    def _trusted_pitch(self, mono: PreparedMono) -> float | None:
        return _trusted(self.reader.read(mono), trusted_reliability=self.reader.trusted_reliability)


def _trusted(reading: PitchReading | None, *, trusted_reliability: float) -> float | None:
    """A reading's pitch when its reader trusts it at least `trusted_reliability`, and None otherwise."""
    if reading is None or reading.reliability < trusted_reliability:
        return None
    return reading.semitones
