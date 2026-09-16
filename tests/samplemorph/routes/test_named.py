from __future__ import annotations

from pathlib import Path

import pytest

from samplemorph.pipeline import RouteChoice
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.named import (
    RouteSelection,
    blend_route,
    envelope_route,
    partials_route,
    select_route,
    transport_route,
)

LATENT_NAMES = RouteChoice(
    model_name="pca", vocoder_name="pghi", restorer_name="restorer", morpher_name="linear", device="cpu"
)


def _selection(kind: RouteKind) -> RouteSelection:
    return RouteSelection(kind=kind, latent=LATENT_NAMES, profile_name="stepped", excitation_name="second")


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (RouteKind.TRANSPORT, "transport"),
        (RouteKind.BLEND, "blend"),
        (RouteKind.PARTIALS, "partials-stepped"),
        (RouteKind.ENVELOPE, "envelope-second"),
    ],
)
def test_a_selection_names_the_route_it_renders_through(tmp_path: Path, kind: RouteKind, name: str) -> None:
    named = select_route(tmp_path, _selection(kind))

    assert named.kind is kind
    assert named.name == name


def test_a_fingerprint_stays_put_for_one_route_and_tells_the_others_apart() -> None:
    fingerprints = [
        route.fingerprint
        for route in (
            envelope_route("first"),
            envelope_route("second"),
            partials_route("glide"),
            partials_route("crossfade"),
            transport_route(),
            blend_route(),
        )
    ]

    assert envelope_route("first").fingerprint == fingerprints[0]
    assert len(set(fingerprints)) == len(fingerprints)


def test_a_route_s_description_names_the_settings_it_reads() -> None:
    named = envelope_route("halfway")

    assert named.description["envelope_settings"] == {"coefficient_count": 40, "floor_db": 80.0, "switch_weight": 0.5}
