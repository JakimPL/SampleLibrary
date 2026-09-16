from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from samplemorph.partials.paths import FadeLaw, PitchPath, fade_progress
from samplemorph.partials.presets import DEFAULT_PROFILE_NAME, PROFILE_PRESETS
from samplemorph.partials.profile import AspectCurve, AspectCurves, Correspondence, CurveShape, MorphProfile

TOLERANCE: Final[float] = 1e-9


@dataclass(frozen=True)
class CurveCase:
    name: str
    curve: AspectCurve
    weight: float
    stands: float


CURVE_CASES = (
    CurveCase("a linear curve moves with the morph", AspectCurve(), 0.25, 0.25),
    CurveCase("a curve holds until it starts", AspectCurve(start=0.5), 0.25, 0.0),
    CurveCase("a curve is there once it ends", AspectCurve(end=0.5), 0.75, 1.0),
    CurveCase("a curve crosses the middle of its own stretch", AspectCurve(start=0.25, end=0.75), 0.5, 0.5),
    CurveCase("an eased curve leaves rest", AspectCurve(shape=CurveShape.EASED), 0.25, 0.15625),
    CurveCase("an eased curve stands halfway at the middle", AspectCurve(shape=CurveShape.EASED), 0.5, 0.5),
)


@pytest.mark.parametrize("case", CURVE_CASES, ids=lambda case: case.name)
def test_a_curve_reads_the_weight_of_the_morph_through_its_own_stretch(case: CurveCase) -> None:
    assert case.curve.at(case.weight) == pytest.approx(case.stands, abs=TOLERANCE)


@pytest.mark.parametrize("curve", (AspectCurve(), AspectCurve(start=0.25, end=0.75, shape=CurveShape.EASED)))
def test_both_ends_of_a_morph_stay_exact_whatever_the_curve(curve: AspectCurve) -> None:
    assert curve.at(0.0) == 0.0
    assert curve.at(1.0) == 1.0


def test_a_curve_ending_where_it_starts_is_refused() -> None:
    with pytest.raises(ValueError, match="start under its end"):
        AspectCurve(start=0.5, end=0.5)


def test_a_curve_starting_past_its_end_is_refused() -> None:
    with pytest.raises(ValueError, match="start under its end"):
        AspectCurve(start=0.75, end=0.25)


def test_a_profile_round_trips_through_the_json_a_render_names_it_by() -> None:
    profile = MorphProfile(
        correspondence=Correspondence(travel_cents=700.0),
        pitch=PitchPath.STEPPED,
        fade=FadeLaw.EARLY,
        curves=AspectCurves(pitch=AspectCurve(start=0.25, end=0.75, shape=CurveShape.EASED)),
    )

    written = profile.model_dump(mode="json")

    assert MorphProfile.model_validate(written) == profile


def test_a_correspondence_names_how_far_a_partial_will_travel_before_fading_comes_cheaper() -> None:
    """The reach falls out of the price of a fade against the price of the distance, which is one currency."""
    correspondence = Correspondence(travel_cents=2400.0, exponent=2.0, fade_price=0.25)

    assert correspondence.travel_reach_cents == pytest.approx(1200.0)


def test_every_preset_names_a_middle_of_its_own() -> None:
    assert DEFAULT_PROFILE_NAME in PROFILE_PRESETS
    assert len(set(PROFILE_PRESETS.values())) == len(PROFILE_PRESETS)


@dataclass(frozen=True)
class FadeCase:
    name: str
    law: FadeLaw
    weight: float
    faded: float


FADE_CASES = (
    FadeCase("the level path fades with the morph", FadeLaw.LEVEL_PATH, 0.5, 0.5),
    FadeCase("an early fade is over by the middle", FadeLaw.EARLY, 0.5, 1.0),
    FadeCase("an early fade is halfway at a quarter", FadeLaw.EARLY, 0.25, 0.5),
    FadeCase("a late fade holds to the middle", FadeLaw.LATE, 0.5, 0.0),
    FadeCase("a late fade is halfway at three quarters", FadeLaw.LATE, 0.75, 0.5),
)


@pytest.mark.parametrize("case", FADE_CASES, ids=lambda case: case.name)
def test_a_partial_meeting_nothing_fades_the_way_its_law_says(case: FadeCase) -> None:
    assert fade_progress(weight=case.weight, law=case.law) == pytest.approx(case.faded, abs=TOLERANCE)


@pytest.mark.parametrize("law", tuple(FadeLaw))
def test_every_fade_law_holds_both_ends_of_the_morph(law: FadeLaw) -> None:
    assert fade_progress(weight=0.0, law=law) == 0.0
    assert fade_progress(weight=1.0, law=law) == 1.0
