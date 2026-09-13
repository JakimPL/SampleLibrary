from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplemorph.geometry import Geometry, constant_q_geometry, log_frequency_geometry, mel_geometry
from samplemorph.training.runs import geometry_parameters


@dataclass(frozen=True)
class GeometryCase:
    """One axis and the names its recorded parameters must and must not carry."""

    name: str
    geometry: Geometry
    named: tuple[str, ...]
    unnamed: tuple[str, ...]


GEOMETRY_CASES = (
    GeometryCase(
        name="log_frequency",
        geometry=log_frequency_geometry(),
        named=("geometry", "anchor", "analysis_window", "fft_length", "hop_length", "bins_per_octave", "band_count"),
        unnamed=(),
    ),
    GeometryCase(
        name="constant_q",
        geometry=constant_q_geometry(),
        named=("geometry", "anchor", "fft_length", "hop_length", "bins_per_octave", "band_count"),
        unnamed=("analysis_window",),
    ),
    GeometryCase(
        name="mel",
        geometry=mel_geometry(),
        named=("geometry", "anchor", "fft_length", "hop_length", "band_count"),
        unnamed=("analysis_window", "bins_per_octave"),
    ),
)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_the_recorded_parameters_name_what_tells_one_grid_from_another(case: GeometryCase) -> None:
    parameters = geometry_parameters(case.geometry)

    assert set(case.named) <= set(parameters)
    assert not set(case.unnamed) & set(parameters)
    assert parameters["geometry"] == case.geometry.kind
    assert parameters["anchor"] == case.geometry.anchor.value
    assert all(isinstance(value, str) for value in parameters.values())
