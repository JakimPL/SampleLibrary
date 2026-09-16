from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.partials.model import SinusoidalModel, analyze_model
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.settings import PartialSettings
from samplemorph.routes.route import HeardMono


@dataclass(frozen=True)
class PartialRoute:
    """The route that sounds each end's partials as oscillators and carries the rest of both sounds by transport.

    Each end is read once into partials over a residual, and the profile says what the middle of the
    two is: which partial meets which, one pairing for the whole path. A pair of sounds that holds no
    partial travels exactly as the transport route carries it.
    """

    morph: PartialMorph
    partial_settings: PartialSettings

    def prepare(self, heard: HeardMono) -> SinusoidalModel:
        return analyze_model(
            heard.mono,
            rate_hz=heard.rate_hz,
            geometry=self.morph.geometry,
            transport_settings=self.morph.settings,
            partial_settings=self.partial_settings,
        )

    def render(self, first: SinusoidalModel, second: SinusoidalModel, *, weight: float) -> NDArray[np.float64]:
        return self.morph.between(first, second, weight=weight)
