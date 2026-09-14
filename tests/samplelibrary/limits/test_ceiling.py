from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplelibrary.limits.ceiling import MalformedCeiling, MemoryCeiling


@dataclass(frozen=True)
class CeilingCase:
    written: str
    byte_count: int | None


@pytest.mark.parametrize(
    "case",
    [
        CeilingCase("16G", 16 * 1024**3),
        CeilingCase("512M", 512 * 1024**2),
        CeilingCase("2T", 2 * 1024**4),
        CeilingCase("1024", 1024),
        CeilingCase(" 8g ", 8 * 1024**3),
        CeilingCase("none", None),
        CeilingCase("None", None),
    ],
    ids=lambda case: case.written,
)
def test_a_ceiling_reads_the_memory_it_names(case: CeilingCase) -> None:
    ceiling = MemoryCeiling.parse(case.written)

    assert ceiling.byte_count == case.byte_count
    assert ceiling.enforced is (case.byte_count is not None)


@pytest.mark.parametrize("written", ["", "16GB", "-1", "0", "16 G", "sixteen", "1.5G"], ids=repr)
def test_a_ceiling_written_another_way_is_refused(written: str) -> None:
    with pytest.raises(MalformedCeiling):
        MemoryCeiling.parse(written)


@pytest.mark.parametrize("written", ["16G", "512M", "none", "1025"], ids=repr)
def test_a_ceiling_reads_back_as_it_was_written(written: str) -> None:
    assert MemoryCeiling.parse(str(MemoryCeiling.parse(written))) == MemoryCeiling.parse(written)
