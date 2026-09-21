from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from sampledescriptor.geometry import Anchor, GridGeometry, grid_geometry
from sampledescriptor.registries import canonicalizer_for_geometry
from samplemorph.geometry import REFERENCE_FREQUENCY_HZ

REFERENCE_BAND_TOLERANCE_HZ = 40.0


def test_the_grid_shape_pairs_the_analyzed_bands_and_their_headroom_with_the_time_columns() -> None:
    geometry = grid_geometry()

    assert geometry.grid_shape == (
        geometry.band_count + 2 * geometry.shift_headroom_bands,
        geometry.time_columns,
    )


@pytest.mark.parametrize("anchor", (Anchor.LOUDEST, Anchor.FUNDAMENTAL), ids=lambda anchor: anchor.value)
def test_the_headroom_holds_the_largest_translation_an_anchoring_rule_allows(anchor: Anchor) -> None:
    """Alignment moves content by at most this much, so the picture keeps every band it analyzed."""
    geometry = grid_geometry(anchor=anchor)

    assert geometry.shift_headroom_bands == round(geometry.maximum_shift_semitones * geometry.bands_per_semitone)


def test_a_grid_nothing_moves_is_exactly_as_tall_as_the_analysis() -> None:
    geometry = grid_geometry(anchor=Anchor.NONE)

    assert geometry.shift_headroom_bands == 0
    assert geometry.grid_shape == (geometry.band_count, geometry.time_columns)


def test_the_reference_band_sits_at_the_reference_frequency() -> None:
    """Alignment moves a sample's strongest band here, so it has to be the band it claims to be."""
    geometry = grid_geometry()

    frequency = geometry.band_frequencies[geometry.reference_band]

    assert frequency == pytest.approx(REFERENCE_FREQUENCY_HZ, abs=REFERENCE_BAND_TOLERANCE_HZ)


def test_one_semitone_spans_a_positive_number_of_bands() -> None:
    assert grid_geometry().bands_per_semitone > 0.0


@pytest.mark.parametrize("anchor", tuple(Anchor), ids=lambda anchor: anchor.value)
def test_the_anchor_survives_a_round_trip_and_rebuilds_the_same_canonicalizer(anchor: Anchor) -> None:
    """A stored model names the anchor its grids were aligned by, so a rebuild aligns the same way."""
    geometry = grid_geometry(anchor=anchor)

    restored = TypeAdapter(GridGeometry).validate_json(geometry.model_dump_json())

    assert restored == geometry
    assert canonicalizer_for_geometry(restored).geometry.anchor is anchor
