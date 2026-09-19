from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplemorph.measurement.pitch.residuals import Residual, residual_of


@dataclass(frozen=True)
class ResidualCase:
    error_semitones: float
    residual: Residual


CASES = (
    ResidualCase(0.3, Residual.WITHIN),
    ResidualCase(-0.5, Residual.WITHIN),
    ResidualCase(0.8, Residual.OFF),
    ResidualCase(12.4, Residual.OCTAVE),
    ResidualCase(-24.9, Residual.OCTAVE),
    ResidualCase(7.2, Residual.FIFTH),
    ResidualCase(-19.0, Residual.FIFTH),
    ResidualCase(5.0, Residual.FIFTH),
    ResidualCase(3.0, Residual.OFF),
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.error_semitones:+g}")
def test_an_error_is_named_by_the_interval_it_lands_near(case: ResidualCase) -> None:
    assert residual_of(case.error_semitones) is case.residual
