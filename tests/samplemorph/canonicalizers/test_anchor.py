from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import Anchor
from samplemorph.images import SoundImage
from samplemorph.registries import CANONICALIZER_REGISTRY
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone, noise_burst

REFERENCE_FREQUENCY_HZ = 440.0
RETUNING_SEMITONES = 7.0
TOLERANCE_SEMITONES = 1.0
TOLERANCE_BANDS = 1.5
SECOND_HARMONIC_LOUDEST = (0.3, 1.0, 0.5, 0.25)
MISSING_FUNDAMENTAL = (0.0, 1.0, 0.8, 0.6, 0.5)


@dataclass(frozen=True)
class AnchorCase:
    """One registered axis, built under any anchor rule."""

    name: str

    def build(self, anchor: Anchor) -> Canonicalizer:
        return CANONICALIZER_REGISTRY[self.name](anchor=anchor)


ANCHOR_CASES = tuple(AnchorCase(name=name) for name in sorted(CANONICALIZER_REGISTRY))


def assert_anchored_at(image: SoundImage, frequency_hz: float) -> None:
    """The recorded translation puts the anchor within a band or so of `frequency_hz`, on the axis's own bands."""
    geometry = image.geometry
    band = int(np.argmin(np.abs(geometry.band_frequencies - frequency_hz)))
    expected = (band - geometry.reference_band) / geometry.bands_per_semitone
    assert image.conditioners.translation_semitones == pytest.approx(
        expected, abs=TOLERANCE_BANDS / geometry.bands_per_semitone
    )


@pytest.mark.parametrize("case", ANCHOR_CASES, ids=lambda case: case.name)
def test_no_anchor_keeps_the_picture_where_the_analysis_read_it(case: AnchorCase) -> None:
    """Every band holds its own frequency, the grid is as tall as the analysis, and nothing is recorded as moved."""
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=REFERENCE_FREQUENCY_HZ, weights=SECOND_HARMONIC_LOUDEST)

    image = case.build(Anchor.NONE).canonicalize(prepare_mono(tone))

    geometry = image.geometry
    loudest_band = int(np.argmax(image.grid.mean(axis=1)))
    second_harmonic_band = int(np.argmin(np.abs(geometry.band_frequencies - 2 * REFERENCE_FREQUENCY_HZ)))
    assert image.grid.shape == (geometry.band_count, geometry.time_columns)
    assert image.conditioners.translation_semitones == 0.0
    assert abs(loudest_band - second_harmonic_band) <= TOLERANCE_BANDS


@pytest.mark.parametrize("case", ANCHOR_CASES, ids=lambda case: case.name)
def test_the_loudest_anchor_follows_the_strongest_partial_and_the_fundamental_anchor_the_series(
    case: AnchorCase,
) -> None:
    """A tone whose second harmonic is loudest is anchored an octave apart by the two rules."""
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=REFERENCE_FREQUENCY_HZ, weights=SECOND_HARMONIC_LOUDEST)

    by_loudest = case.build(Anchor.LOUDEST).canonicalize(prepare_mono(tone))
    by_fundamental = case.build(Anchor.FUNDAMENTAL).canonicalize(prepare_mono(tone))

    assert_anchored_at(by_loudest, 2 * REFERENCE_FREQUENCY_HZ)
    assert_anchored_at(by_fundamental, REFERENCE_FREQUENCY_HZ)


@pytest.mark.parametrize("case", ANCHOR_CASES, ids=lambda case: case.name)
def test_the_fundamental_anchor_finds_a_series_whose_fundamental_is_silent(case: AnchorCase) -> None:
    """The harmonics alone say where the series is built, an octave below the reference here."""
    tone = harmonic_tone(TEST_FRAME_COUNT, frequency=REFERENCE_FREQUENCY_HZ / 2, weights=MISSING_FUNDAMENTAL)

    image = case.build(Anchor.FUNDAMENTAL).canonicalize(prepare_mono(tone))

    assert_anchored_at(image, REFERENCE_FREQUENCY_HZ / 2)


def test_the_fundamental_anchor_moves_with_a_retuning() -> None:
    """Reading the same waveform faster raises its anchor by the retuning, so the grid stays put."""
    canonicalizer = CANONICALIZER_REGISTRY["log_frequency"](anchor=Anchor.FUNDAMENTAL)
    tone = harmonic_tone(4 * TEST_FRAME_COUNT, frequency=REFERENCE_FREQUENCY_HZ, weights=SECOND_HARMONIC_LOUDEST)

    stored = canonicalizer.canonicalize(prepare_mono(tone))
    retuned = canonicalizer.canonicalize(prepare_mono(resample_by_semitones(tone, semitones=RETUNING_SEMITONES)))

    assert retuned.conditioners.translation_semitones - stored.conditioners.translation_semitones == pytest.approx(
        RETUNING_SEMITONES, abs=TOLERANCE_SEMITONES
    )
    assert np.corrcoef(stored.grid.ravel(), retuned.grid.ravel())[0, 1] > 0.9


@pytest.mark.parametrize("case", ANCHOR_CASES, ids=lambda case: case.name)
def test_the_fundamental_anchor_takes_a_noise_burst_through_the_same_path(case: AnchorCase) -> None:
    image = case.build(Anchor.FUNDAMENTAL).canonicalize(prepare_mono(noise_burst(TEST_FRAME_COUNT, seed=2)))

    assert np.all(np.isfinite(image.grid))
    assert image.grid.max() <= 1.0
