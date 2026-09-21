from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from pydantic import JsonValue

from samplemorph.coordinates.readers import subharmonic_reader
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import Timeline
from samplemorph.geometry import log_frequency_geometry
from samplemorph.rendering import RENDER_REVISION
from samplemorph.routes.envelope import EnvelopeRoute
from samplemorph.routes.selection import Glide, RouteSelection
from samplemorph.transport.settings import TransportSettings

ENVELOPE_NAME: Final[str] = "envelope"


@dataclass(frozen=True)
class NamedRoute:
    """The route a selection names, ready to render, under the name a status knows it by, with the JSON that says what it is.

    The name tells the excitation, the timeline and the glide a route renders with apart, and the
    description names every setting the route reads, which is what it takes to render the same
    sound again.
    """

    name: str
    route: EnvelopeRoute
    description: dict[str, JsonValue]

    @property
    def fingerprint(self) -> str:
        """One digest naming what this route renders: the rendering code's revision, the name, and everything the description says."""
        named = "|".join((str(RENDER_REVISION), self.name, json.dumps(self.description, sort_keys=True)))
        return hashlib.sha256(named.encode()).hexdigest()


def select_route(selection: RouteSelection) -> NamedRoute:
    """The envelope route a selection names, gliding when it names a reader to glide by."""
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    envelope_settings = selection.envelope
    description: dict[str, JsonValue] = {
        "geometry": geometry.model_dump(mode="json"),
        "settings": settings.model_dump(mode="json"),
        "envelope_settings": envelope_settings.model_dump(mode="json"),
    }
    name = _envelope_name(selection)
    reader = None
    match selection.glide:
        case Glide.SUBHARMONIC:
            reader = subharmonic_reader()
            description["pitch_reader"] = reader.describe()
            name = f"{name}-glide-{reader.name}"
        case None:
            pass
    return NamedRoute(
        name=name,
        route=EnvelopeRoute(
            path=EnvelopePath(envelope_settings=envelope_settings), reader=reader, geometry=geometry, settings=settings
        ),
        description=description,
    )


def _envelope_name(selection: RouteSelection) -> str:
    """What an envelope route is known by: whose excitation it sounds, and whose course it holds when it holds one."""
    envelope_settings = selection.envelope
    sounded = f"{ENVELOPE_NAME}-{envelope_settings.excitation.value}"
    match envelope_settings.timeline:
        case Timeline.MORPHED:
            return sounded
        case Timeline.FIRST | Timeline.SECOND:
            return f"{sounded}-on-{envelope_settings.timeline.value}"
