from __future__ import annotations

from enum import StrEnum, unique

from samplemorph.routes.analysis import AnalysisRoute
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.route import HeardMono, PreparedPair, prepare_pair

ComparableRoute = LatentRoute | AnalysisRoute


@unique
class RouteKind(StrEnum):
    """The routes a morph can take between two sounds.

    `LATENT` runs through a stored codec's latent space; `TRANSPORT` carries every feature of one
    analysis to the other's; `BLEND` crossfades the two analyses in decibels, the control the
    transport is judged against.
    """

    LATENT = "latent"
    TRANSPORT = "transport"
    BLEND = "blend"


def pair_through(route: ComparableRoute, first: HeardMono, second: HeardMono) -> PreparedPair:
    """Two ends prepared by whichever route renders between them."""
    match route:
        case LatentRoute():
            return prepare_pair(route, first, second)
        case AnalysisRoute():
            return prepare_pair(route, first, second)
