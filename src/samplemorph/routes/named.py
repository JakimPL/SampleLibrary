from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from samplemorph.coordinates.readers import PitchReader
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import EnvelopeSettings, Timeline
from samplemorph.geometry import log_frequency_geometry
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.partials.settings import PartialSettings
from samplemorph.pipeline import LoadedRoute, latent_route_description, load_route
from samplemorph.rendering import RENDER_REVISION
from samplemorph.routes.analysis import AnalysisRoute, SpectralPath
from samplemorph.routes.gliding import GlidingRoute
from samplemorph.routes.kinds import ComparableRoute, RouteKind
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.partials import PartialRoute
from samplemorph.routes.selection import PROCESSOR, RouteSelection
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings


@dataclass(frozen=True)
class NamedRoute:
    """One route ready to render, under the name a manifest, a folder or a status knows it by, with the JSON that says what it is.

    Several routes share a kind, a partials route per profile and an envelope route per excitation
    among them, and the name tells them apart. `device` is where the route's work runs, and the
    description names every setting, preset and stored file the route reads, which is what it takes
    to render the same sound again.
    """

    kind: RouteKind
    name: str
    route: ComparableRoute
    device: str
    description: dict[str, JsonValue]

    @property
    def fingerprint(self) -> str:
        """One digest naming what this route renders: the rendering code's revision, the name, and everything the description says.

        The latent route's description carries the digest of every file it was loaded from, so a
        model retrained under the same name renders under another fingerprint, as a route whose
        settings changed does.
        """
        named = "|".join((str(RENDER_REVISION), self.name, json.dumps(self.description, sort_keys=True)))
        return hashlib.sha256(named.encode()).hexdigest()


def select_route(library_root: Path, selection: RouteSelection) -> NamedRoute:
    """The one route a selection names, the latent route loaded from the library.

    Raises:
        FileNotFoundError: the latent route's model, or the restorer its vocoder reads, is stored under no such name.
        ModelFileChanged: a model file was written while the latent route was loaded from it.
    """
    match selection.route:
        case RouteKind.LATENT:
            return latent_route(load_route(library_root, selection.latent))
        case RouteKind.TRANSPORT:
            return transport_route()
        case RouteKind.BLEND:
            return blend_route()
        case RouteKind.PARTIALS:
            return partials_route(selection.partials.profile)
        case RouteKind.ENVELOPE:
            return envelope_route(selection.envelope)


def latent_route(loaded: LoadedRoute) -> NamedRoute:
    """The route through a loaded codec's latent space, described by the model, the vocoder and the files it read."""
    return NamedRoute(
        kind=RouteKind.LATENT,
        name=RouteKind.LATENT.value,
        route=LatentRoute(loaded.route),
        device=loaded.choice.device,
        description=latent_route_description(loaded),
    )


def transport_route() -> NamedRoute:
    """The transport on the analyses' default geometry and settings."""
    return _analysis_route(RouteKind.TRANSPORT, name=RouteKind.TRANSPORT.value, path=transport, described={})


def blend_route() -> NamedRoute:
    """The decibel crossfade every other route is judged against, on the analyses' default geometry and settings."""
    return _analysis_route(RouteKind.BLEND, name=RouteKind.BLEND.value, path=blend, described={})


def envelope_route(envelope_settings: EnvelopeSettings) -> NamedRoute:
    """The envelope morph under the settings given, on the analyses' default geometry and settings, named by what it sounds."""
    return _analysis_route(
        RouteKind.ENVELOPE,
        name=_envelope_name(envelope_settings),
        path=EnvelopePath(envelope_settings=envelope_settings),
        described={"envelope_settings": envelope_settings.model_dump(mode="json")},
    )


def gliding_envelope_route(envelope_settings: EnvelopeSettings, *, reader: PitchReader) -> NamedRoute:
    """The envelope route under the settings given with its excitation gliding between the pitches `reader` finds, named by both."""
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    return NamedRoute(
        kind=RouteKind.ENVELOPE,
        name=f"{_envelope_name(envelope_settings)}-glide-{reader.name}",
        route=GlidingRoute(
            path=EnvelopePath(envelope_settings=envelope_settings),
            reader=reader,
            geometry=geometry,
            settings=settings,
        ),
        device=PROCESSOR,
        description={
            "geometry": geometry.model_dump(mode="json"),
            "settings": settings.model_dump(mode="json"),
            "envelope_settings": envelope_settings.model_dump(mode="json"),
            "pitch_reader": reader.description(),
        },
    )


def _envelope_name(envelope_settings: EnvelopeSettings) -> str:
    """What an envelope route is known by: whose excitation it sounds, and whose course it holds when it holds one."""
    sounded = f"{RouteKind.ENVELOPE.value}-{envelope_settings.excitation.value}"
    match envelope_settings.timeline:
        case Timeline.MORPHED:
            return sounded
        case Timeline.FIRST | Timeline.SECOND:
            return f"{sounded}-on-{envelope_settings.timeline.value}"


def partials_route(profile_name: str) -> NamedRoute:
    """The partials route following the profile a preset names, on the analyses' default geometry and settings."""
    profile = PROFILE_PRESETS[profile_name]
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    partial_settings = PartialSettings()
    return NamedRoute(
        kind=RouteKind.PARTIALS,
        name=f"{RouteKind.PARTIALS.value}-{profile_name}",
        route=PartialRoute(
            morph=PartialMorph(profile=profile, geometry=geometry, settings=settings),
            partial_settings=partial_settings,
        ),
        device=PROCESSOR,
        description={
            "geometry": geometry.model_dump(mode="json"),
            "settings": settings.model_dump(mode="json"),
            "partial_settings": partial_settings.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
        },
    )


def _analysis_route(kind: RouteKind, *, name: str, path: SpectralPath, described: dict[str, JsonValue]) -> NamedRoute:
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    return NamedRoute(
        kind=kind,
        name=name,
        route=AnalysisRoute(path=path, geometry=geometry, settings=settings),
        device=PROCESSOR,
        description={
            "geometry": geometry.model_dump(mode="json"),
            "settings": settings.model_dump(mode="json"),
            **described,
        },
    )
