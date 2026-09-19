from __future__ import annotations

from pathlib import Path

import pytest

from samplemorph.coordinates.readers import pyin_reader, subharmonic_reader
from samplemorph.envelope.settings import EnvelopeSettings, Excitation, Timeline
from samplemorph.pipeline import RouteChoice
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.named import (
    blend_route,
    envelope_route,
    gliding_envelope_route,
    partials_route,
    select_route,
    transport_route,
)
from samplemorph.routes.selection import PartialsSelection, RouteSelection

LATENT_NAMES = RouteChoice(
    model_name="pca", vocoder_name="pghi", restorer_name="restorer", morpher_name="linear", device="cpu"
)
KEEPS_FIRST = EnvelopeSettings(excitation=Excitation.FIRST)
SOUNDS_BOTH = EnvelopeSettings(excitation=Excitation.BOTH)
SMOOTHER = EnvelopeSettings(excitation=Excitation.FIRST, coefficient_count=12)
HELD_TO_FIRST = EnvelopeSettings(excitation=Excitation.FIRST, timeline=Timeline.FIRST)
HELD_TO_SECOND = EnvelopeSettings(excitation=Excitation.FIRST, timeline=Timeline.SECOND)


def _selection(kind: RouteKind) -> RouteSelection:
    return RouteSelection(
        route=kind,
        latent=LATENT_NAMES,
        partials=PartialsSelection(profile="stepped"),
        envelope=EnvelopeSettings(excitation=Excitation.SECOND),
    )


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
            envelope_route(KEEPS_FIRST),
            envelope_route(SOUNDS_BOTH),
            envelope_route(SMOOTHER),
            envelope_route(HELD_TO_FIRST),
            envelope_route(HELD_TO_SECOND),
            gliding_envelope_route(KEEPS_FIRST, reader=subharmonic_reader()),
            gliding_envelope_route(KEEPS_FIRST, reader=pyin_reader()),
            gliding_envelope_route(SOUNDS_BOTH, reader=subharmonic_reader()),
            partials_route("glide"),
            partials_route("crossfade"),
            transport_route(),
            blend_route(),
        )
    ]

    assert envelope_route(KEEPS_FIRST).fingerprint == fingerprints[0]
    assert len(set(fingerprints)) == len(fingerprints)


def test_a_route_s_description_names_the_settings_it_reads() -> None:
    settings = EnvelopeSettings(excitation=Excitation.BOTH, coefficient_count=12)

    named = envelope_route(settings)

    assert named.name == "envelope-both"
    assert named.description["envelope_settings"] == settings.model_dump(mode="json")


@pytest.mark.parametrize(
    ("settings", "name"),
    [
        (KEEPS_FIRST, "envelope-first"),
        (HELD_TO_FIRST, "envelope-first-on-first"),
        (HELD_TO_SECOND, "envelope-first-on-second"),
    ],
    ids=("a morphed course", "the first sound's course", "the second sound's course"),
)
def test_an_envelope_route_holding_a_course_is_named_apart(settings: EnvelopeSettings, name: str) -> None:
    assert envelope_route(settings).name == name


def test_a_gliding_envelope_route_is_named_by_its_reader_and_describes_it() -> None:
    reader = subharmonic_reader()

    named = gliding_envelope_route(HELD_TO_FIRST, reader=reader)

    assert named.kind is RouteKind.ENVELOPE
    assert named.name == "envelope-first-on-first-glide-subharmonic"
    assert named.description["pitch_reader"] == reader.description()
