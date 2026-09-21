from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import EnvelopeSettings, Excitation, Timeline
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.transport.conftest import (
    BIN_SPACING_HZ,
    CLIP_FRAMES,
    GEOMETRY,
    analysis_of,
    middle_spectrum,
    tone,
)

LOW_HZ: Final[float] = 300.0
HIGH_HZ: Final[float] = 450.0
LOBE_REACH_BINS: Final[int] = 2
SOUNDING_WITHIN_DB: Final[float] = 12.0
SILENT_UNDER_DB: Final[float] = 20.0
FIRST_END: Final[float] = 0.0
MIDPOINT: Final[float] = 0.5
SECOND_END: Final[float] = 1.0
REGISTER_EDGE_HZ: Final[float] = 700.0
DULL_WEIGHTS: Final[tuple[float, ...]] = (1.0, 0.1, 0.01, 0.001)
RECONSTRUCTION_RELATIVE_TOLERANCE: Final[float] = 1e-3
RECONSTRUCTION_FLOOR_SHARE: Final[float] = 1e-4
KEEPS_FIRST: Final[EnvelopeSettings] = EnvelopeSettings(excitation=Excitation.FIRST)
KEEPS_SECOND: Final[EnvelopeSettings] = EnvelopeSettings(excitation=Excitation.SECOND)
SOUNDS_BOTH: Final[EnvelopeSettings] = EnvelopeSettings(excitation=Excitation.BOTH)
LONG_CLIP_FRAMES: Final[int] = CLIP_FRAMES * 2
PATH_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.25, 0.5, 0.75, 1.0)
MIDPOINT_INDEX: Final[int] = 2


@dataclass(frozen=True)
class OwnEndCase:
    """An end of the path at which the excitation sounding is that of the sound the end belongs to."""

    settings: EnvelopeSettings
    weight: float


@dataclass(frozen=True)
class FarEndCase:
    """An end of the path at which the kept excitation belongs to the other sound."""

    settings: EnvelopeSettings
    weight: float
    kept_hz: float
    dropped_hz: float


@pytest.fixture(scope="module")
def low_tone() -> TransportAnalysis:
    return analysis_of(tone(LOW_HZ))


@pytest.fixture(scope="module")
def high_tone() -> TransportAnalysis:
    return analysis_of(tone(HIGH_HZ))


@pytest.fixture(scope="module")
def long_tone() -> TransportAnalysis:
    return analysis_of(tone(HIGH_HZ, frame_count=LONG_CLIP_FRAMES))


def _sample_count(
    first: TransportAnalysis, second: TransportAnalysis, *, weight: float, settings: EnvelopeSettings
) -> int:
    path = EnvelopePath(envelope_settings=settings)
    return path(first, second, weight=weight, geometry=GEOMETRY, settings=TransportSettings()).sample_count


def _magnitude(
    first: TransportAnalysis, second: TransportAnalysis, *, weight: float, settings: EnvelopeSettings
) -> NDArray[np.float32]:
    path = EnvelopePath(envelope_settings=settings)
    return path(first, second, weight=weight, geometry=GEOMETRY, settings=TransportSettings()).magnitude


def _spectrum(
    first: TransportAnalysis, second: TransportAnalysis, *, weight: float, settings: EnvelopeSettings
) -> NDArray[np.float64]:
    return middle_spectrum(_magnitude(first, second, weight=weight, settings=settings))


def _level_near(spectrum: NDArray[np.float64], frequency_hz: float) -> float:
    """The loudest bin within reach of a frequency, in decibels under the whole spectrum's peak."""
    center = int(round(frequency_hz / BIN_SPACING_HZ))
    nearby = spectrum[center - LOBE_REACH_BINS : center + LOBE_REACH_BINS + 1]
    return float(10.0 * np.log10(nearby.max() / spectrum.max()))


def _upper_register_share(spectrum: NDArray[np.float64]) -> float:
    edge = int(round(REGISTER_EDGE_HZ / BIN_SPACING_HZ))
    return float(spectrum[edge:].sum() / spectrum[:edge].sum())


@pytest.mark.parametrize(
    "case",
    (
        OwnEndCase(KEEPS_FIRST, FIRST_END),
        OwnEndCase(KEEPS_SECOND, SECOND_END),
        OwnEndCase(SOUNDS_BOTH, FIRST_END),
        OwnEndCase(SOUNDS_BOTH, SECOND_END),
    ),
    ids=("first kept at its end", "second kept at its end", "both at the first end", "both at the second end"),
)
def test_an_end_whose_own_excitation_sounds_reconstructs_that_sound_s_analysis(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis, case: OwnEndCase
) -> None:
    expected = np.sqrt((low_tone if case.weight == FIRST_END else high_tone).energy)

    magnitude = _magnitude(low_tone, high_tone, weight=case.weight, settings=case.settings)

    assert magnitude.shape == expected.shape
    assert np.allclose(
        magnitude,
        expected,
        rtol=RECONSTRUCTION_RELATIVE_TOLERANCE,
        atol=RECONSTRUCTION_FLOOR_SHARE * float(expected.max()),
    )


@pytest.mark.parametrize(
    "case",
    (
        FarEndCase(KEEPS_FIRST, SECOND_END, kept_hz=LOW_HZ, dropped_hz=HIGH_HZ),
        FarEndCase(KEEPS_SECOND, FIRST_END, kept_hz=HIGH_HZ, dropped_hz=LOW_HZ),
    ),
    ids=("first kept at the second's end", "second kept at the first's end"),
)
def test_the_far_end_of_a_kept_excitation_sounds_its_own_harmonics_and_none_of_the_other_s(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis, case: FarEndCase
) -> None:
    far_end = _spectrum(low_tone, high_tone, weight=case.weight, settings=case.settings)

    assert _level_near(far_end, case.kept_hz) > -SOUNDING_WITHIN_DB
    assert _level_near(far_end, 2.0 * case.kept_hz) > -SOUNDING_WITHIN_DB
    assert _level_near(far_end, case.dropped_hz) < -SILENT_UNDER_DB


def test_the_far_end_of_a_kept_excitation_wears_the_other_sound_s_envelope(low_tone: TransportAnalysis) -> None:
    dull = analysis_of(tone(LOW_HZ, weights=DULL_WEIGHTS))
    bright_share = np.log(_upper_register_share(middle_spectrum(np.sqrt(low_tone.energy))))
    dull_share = np.log(_upper_register_share(middle_spectrum(np.sqrt(dull.energy))))

    far_end_share = np.log(_upper_register_share(_spectrum(low_tone, dull, weight=SECOND_END, settings=KEEPS_FIRST)))

    assert abs(far_end_share - dull_share) < abs(far_end_share - bright_share)


def test_the_midpoint_sounds_the_first_tone_s_harmonics_and_none_of_the_second_s(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    kept = _spectrum(low_tone, high_tone, weight=MIDPOINT, settings=KEEPS_FIRST)

    assert _level_near(kept, LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(kept, 2.0 * LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(kept, HIGH_HZ) < -SILENT_UNDER_DB


def test_the_second_tone_s_excitation_sounds_throughout_when_kept(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    kept = _spectrum(low_tone, high_tone, weight=MIDPOINT, settings=KEEPS_SECOND)

    assert _level_near(kept, HIGH_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(kept, LOW_HZ) < -SILENT_UNDER_DB


def test_both_excitations_sound_at_the_midpoint_when_crossfaded(
    low_tone: TransportAnalysis, high_tone: TransportAnalysis
) -> None:
    crossfaded = _spectrum(low_tone, high_tone, weight=MIDPOINT, settings=SOUNDS_BOTH)

    assert _level_near(crossfaded, LOW_HZ) > -SOUNDING_WITHIN_DB
    assert _level_near(crossfaded, HIGH_HZ) > -SOUNDING_WITHIN_DB


def test_the_envelope_moves_the_balance_of_registers_between_the_ends(low_tone: TransportAnalysis) -> None:
    dull = analysis_of(tone(LOW_HZ, weights=DULL_WEIGHTS))

    bright_share = _upper_register_share(middle_spectrum(np.sqrt(low_tone.energy)))
    dull_share = _upper_register_share(middle_spectrum(np.sqrt(dull.energy)))
    middle_share = _upper_register_share(_spectrum(low_tone, dull, weight=MIDPOINT, settings=KEEPS_FIRST))

    assert dull_share < middle_share < bright_share


@pytest.mark.parametrize("settings", (KEEPS_FIRST, KEEPS_SECOND, SOUNDS_BOTH), ids=("first", "second", "both"))
def test_a_tone_meeting_silence_renders_finite(low_tone: TransportAnalysis, settings: EnvelopeSettings) -> None:
    silence = analysis_of(np.zeros(CLIP_FRAMES))

    for weight in (FIRST_END, MIDPOINT, SECOND_END):
        assert np.all(np.isfinite(_magnitude(low_tone, silence, weight=weight, settings=settings)))


def test_a_weight_outside_the_path_is_refused(low_tone: TransportAnalysis, high_tone: TransportAnalysis) -> None:
    with pytest.raises(ValueError, match="between weights 0 and 1"):
        EnvelopePath(envelope_settings=KEEPS_FIRST)(
            low_tone, high_tone, weight=1.5, geometry=GEOMETRY, settings=TransportSettings()
        )


@pytest.mark.parametrize(
    "timeline",
    (Timeline.FIRST, Timeline.SECOND),
    ids=("the first sound's course", "the second sound's course"),
)
def test_a_held_course_lasts_as_long_as_the_sound_whose_course_it_is(
    low_tone: TransportAnalysis, long_tone: TransportAnalysis, timeline: Timeline
) -> None:
    held = low_tone if timeline is Timeline.FIRST else long_tone
    settings = EnvelopeSettings(timeline=timeline)

    lengths = {_sample_count(low_tone, long_tone, weight=weight, settings=settings) for weight in PATH_WEIGHTS}

    assert lengths == {held.sample_count}


def test_a_morphed_course_runs_from_one_length_to_the_other(
    low_tone: TransportAnalysis, long_tone: TransportAnalysis
) -> None:
    settings = EnvelopeSettings(timeline=Timeline.MORPHED)

    lengths = [_sample_count(low_tone, long_tone, weight=weight, settings=settings) for weight in PATH_WEIGHTS]

    assert lengths[0] == low_tone.sample_count
    assert lengths[-1] == long_tone.sample_count
    assert lengths == sorted(lengths)
    assert low_tone.sample_count < lengths[MIDPOINT_INDEX] < long_tone.sample_count
