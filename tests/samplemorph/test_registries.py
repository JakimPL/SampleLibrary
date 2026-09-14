from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplemorph.registries import CANONICALIZER_REGISTRY, RENDERABLE_CANONICALIZER_NAMES
from samplemorph.vocoders.pghi import gaussian_log_frequency


@dataclass(frozen=True)
class AxisCase:
    name: str

    @property
    def renderable(self) -> bool:
        return self.name in RENDERABLE_CANONICALIZER_NAMES


@pytest.mark.parametrize(
    "case", [AxisCase(name) for name in sorted(CANONICALIZER_REGISTRY)], ids=lambda case: case.name
)
def test_an_axis_is_named_renderable_exactly_when_a_vocoder_reads_it(case: AxisCase) -> None:
    geometry = CANONICALIZER_REGISTRY[case.name]().geometry

    if case.renderable:
        assert gaussian_log_frequency(geometry) == geometry
    else:
        with pytest.raises(ValueError, match="phase gradient heap integration"):
            gaussian_log_frequency(geometry)
