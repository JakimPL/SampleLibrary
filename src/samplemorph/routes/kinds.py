from __future__ import annotations

from enum import StrEnum, unique

from samplemorph.routes.analysis import AnalysisRoute
from samplemorph.routes.gliding import GlidingRoute
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.partials import PartialRoute
from samplemorph.routes.route import HeardMono, PreparedPair, prepare_pair

ComparableRoute = LatentRoute | AnalysisRoute | GlidingRoute | PartialRoute


@unique
class RouteKind(StrEnum):
    """The routes a morph can take between two sounds.

    `LATENT` runs through a stored codec's latent space; `TRANSPORT` carries every feature of one
    analysis to the other's; `BLEND` crossfades the two analyses in decibels, the control the
    transport is judged against; `PARTIALS` sounds the partials of both ends as oscillators on the
    path a profile draws, and transports what is left of them; `ENVELOPE` moves the spectral
    envelope between the two analyses and keeps one sound's excitation whole under it, at its own
    pitch or gliding to the other sound's.
    """

    LATENT = "latent"
    TRANSPORT = "transport"
    BLEND = "blend"
    PARTIALS = "partials"
    ENVELOPE = "envelope"


def pair_through(route: ComparableRoute, first: HeardMono, second: HeardMono) -> PreparedPair:
    """Two ends prepared by whichever route renders between them."""
    match route:
        case LatentRoute():
            return prepare_pair(route, first, second)
        case AnalysisRoute():
            return prepare_pair(route, first, second)
        case GlidingRoute():
            return prepare_pair(route, first, second)
        case PartialRoute():
            return prepare_pair(route, first, second)
