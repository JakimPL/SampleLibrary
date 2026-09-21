from __future__ import annotations

import pytest

from samplemorph.coordinates.readers import subharmonic_reader
from samplemorph.envelope.settings import EnvelopeSettings, Excitation, Timeline
from samplemorph.routes.named import select_route
from samplemorph.routes.selection import Glide, RouteSelection

KEEPS_FIRST = EnvelopeSettings(excitation=Excitation.FIRST)
SOUNDS_BOTH = EnvelopeSettings(excitation=Excitation.BOTH)
SMOOTHER = EnvelopeSettings(excitation=Excitation.FIRST, coefficient_count=12)
HELD_TO_FIRST = EnvelopeSettings(excitation=Excitation.FIRST, timeline=Timeline.FIRST)
HELD_TO_SECOND = EnvelopeSettings(excitation=Excitation.FIRST, timeline=Timeline.SECOND)


def _selection(settings: EnvelopeSettings, *, glide: Glide | None = None) -> RouteSelection:
    return RouteSelection(envelope=settings, glide=glide)


def test_a_fingerprint_stays_put_for_one_route_and_tells_the_others_apart() -> None:
    fingerprints = [
        select_route(selection).fingerprint
        for selection in (
            _selection(KEEPS_FIRST),
            _selection(SOUNDS_BOTH),
            _selection(SMOOTHER),
            _selection(HELD_TO_FIRST),
            _selection(HELD_TO_SECOND),
            _selection(KEEPS_FIRST, glide=Glide.SUBHARMONIC),
            _selection(SOUNDS_BOTH, glide=Glide.SUBHARMONIC),
        )
    ]

    assert select_route(_selection(KEEPS_FIRST)).fingerprint == fingerprints[0]
    assert len(set(fingerprints)) == len(fingerprints)


def test_a_route_s_description_names_the_settings_it_reads() -> None:
    settings = EnvelopeSettings(excitation=Excitation.BOTH, coefficient_count=12)

    named = select_route(_selection(settings))

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
    assert select_route(_selection(settings)).name == name


def test_a_selection_that_names_a_reader_glides_by_it_and_describes_it() -> None:
    named = select_route(_selection(HELD_TO_FIRST, glide=Glide.SUBHARMONIC))

    assert named.name == "envelope-first-on-first-glide-subharmonic"
    assert named.description["pitch_reader"] == subharmonic_reader().describe()
    assert named.route.reader == subharmonic_reader()


def test_a_selection_naming_no_reader_builds_a_route_that_holds_every_pitch() -> None:
    assert select_route(_selection(KEEPS_FIRST)).route.reader is None
