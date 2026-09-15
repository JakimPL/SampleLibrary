from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from samplemorph.images import SampleLatent
from samplemorph.pipeline import MorphRoute, render_morph
from samplemorph.routes.route import HeardMono


@dataclass(frozen=True)
class LatentRoute:
    """The route through a codec's latent space: canonicalize, encode, morph, decode, restore and vocode."""

    route: MorphRoute

    def prepare(self, heard: HeardMono) -> SampleLatent:
        return self.route.codec.encode(self.route.canonicalizer.canonicalize(heard.mono))

    def render(self, first: SampleLatent, second: SampleLatent, *, weight: float) -> NDArray[np.float64]:
        return render_morph(first, second, weight=weight, route=self.route)
