from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplemorph.geometry import (
    REFERENCE_FREQUENCY_HZ,
    SEMITONES_PER_OCTAVE,
    Geometry,
    constant_q_geometry,
    log_frequency_geometry,
    mel_geometry,
)

REFERENCE_BAND_TOLERANCE_HZ = 40.0


@dataclass(frozen=True)
class GeometryCase:
    """One frequency axis, checked against the properties every axis is expected to report."""

    name: str
    geometry: Geometry
    is_exactly_logarithmic: bool


GEOMETRY_CASES = (
    GeometryCase(name="log_frequency", geometry=log_frequency_geometry(), is_exactly_logarithmic=True),
    GeometryCase(name="constant_q", geometry=constant_q_geometry(), is_exactly_logarithmic=True),
    GeometryCase(name="mel", geometry=mel_geometry(), is_exactly_logarithmic=False),
)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_grid_shape_pairs_the_analyzed_bands_and_their_headroom_with_the_time_columns(
    case: GeometryCase,
) -> None:
    geometry = case.geometry

    assert geometry.grid_shape == (
        geometry.band_count + 2 * geometry.shift_headroom_bands,
        geometry.time_columns,
    )


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_headroom_holds_the_largest_translation_the_geometry_allows(case: GeometryCase) -> None:
    """Alignment moves content by at most this much, so the picture keeps every band it analyzed."""
    geometry = case.geometry

    assert geometry.shift_headroom_bands == round(geometry.maximum_shift_semitones * geometry.bands_per_semitone)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_band_frequencies_rise_across_the_axis(case: GeometryCase) -> None:
    frequencies = case.geometry.band_frequencies

    assert frequencies.shape == (case.geometry.band_count,)
    assert np.all(np.diff(frequencies) > 0.0)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_reference_band_sits_at_the_reference_frequency(case: GeometryCase) -> None:
    """Alignment moves a sample's strongest band here, so it has to be the band it claims to be."""
    frequency = case.geometry.band_frequencies[case.geometry.reference_band]

    assert frequency == pytest.approx(REFERENCE_FREQUENCY_HZ, abs=REFERENCE_BAND_TOLERANCE_HZ)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_one_semitone_spans_a_positive_number_of_bands(case: GeometryCase) -> None:
    assert case.geometry.bands_per_semitone > 0.0


@pytest.mark.parametrize(
    "case", [case for case in GEOMETRY_CASES if case.is_exactly_logarithmic], ids=lambda case: case.name
)
def test_a_logarithmic_axis_spaces_every_octave_by_the_same_band_count(case: GeometryCase) -> None:
    """An exactly logarithmic axis is what makes a rate change a whole-band translation."""
    frequencies = case.geometry.band_frequencies
    bands_per_octave = case.geometry.bands_per_semitone * SEMITONES_PER_OCTAVE
    octave_steps = np.log2(frequencies[1:] / frequencies[:-1]) * bands_per_octave

    assert np.allclose(octave_steps, 1.0)


def test_the_mel_axis_spaces_its_low_bands_more_widely_than_a_logarithm_would() -> None:
    """Mel stays close to linear in the bass, which is what its translation error comes from."""
    geometry = mel_geometry()
    frequencies = geometry.band_frequencies

    low_ratio = frequencies[10] / frequencies[9]
    high_ratio = frequencies[-1] / frequencies[-2]

    assert low_ratio > high_ratio
