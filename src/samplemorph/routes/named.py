from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.presets import ENVELOPE_PRESETS
from samplemorph.geometry import log_frequency_geometry
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import PROFILE_PRESETS
from samplemorph.partials.settings import PartialSettings
from samplemorph.pipeline import LoadedRoute, RouteChoice, latent_route_description, load_route
from samplemorph.rendering import RENDER_REVISION
from samplemorph.routes.analysis import AnalysisRoute, SpectralPath
from samplemorph.routes.kinds import ComparableRoute, RouteKind
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.partials import PartialRoute
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings

PROCESSOR: Final[str] = "cpu"


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


@dataclass(frozen=True)
class RouteSelection:
    """Which route one process renders through, with the names each kind reads.

    The latent route reads the stored model and the rest of `latent`, the partials route the profile
    named, and the envelope route the excitation named; the transport and the blend read their
    default settings alone.
    """

    kind: RouteKind
    latent: RouteChoice
    profile_name: str
    excitation_name: str


def select_route(library_root: Path, selection: RouteSelection) -> NamedRoute:
    """The one route a selection names, the latent route loaded from the library.

    Raises:
        FileNotFoundError: the latent route's model, or the restorer its vocoder reads, is stored under no such name.
        ModelFileChanged: a model file was written while the latent route was loaded from it.
    """
    match selection.kind:
        case RouteKind.LATENT:
            return latent_route(load_route(library_root, selection.latent))
        case RouteKind.TRANSPORT:
            return transport_route()
        case RouteKind.BLEND:
            return blend_route()
        case RouteKind.PARTIALS:
            return partials_route(selection.profile_name)
        case RouteKind.ENVELOPE:
            return envelope_route(selection.excitation_name)


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


def envelope_route(excitation_name: str) -> NamedRoute:
    """The envelope morph keeping the excitation a preset names, on the analyses' default geometry and settings."""
    envelope_settings = ENVELOPE_PRESETS[excitation_name]
    return _analysis_route(
        RouteKind.ENVELOPE,
        name=f"{RouteKind.ENVELOPE.value}-{excitation_name}",
        path=EnvelopePath(envelope_settings=envelope_settings),
        described={"envelope_settings": envelope_settings.model_dump(mode="json")},
    )


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
