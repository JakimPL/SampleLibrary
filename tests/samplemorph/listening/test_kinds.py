from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplemorph.listening.kinds import BASS, BASS_DRUM, HI_HAT, LEAD, SNARE, SoundKind


@dataclass(frozen=True)
class NamingCase:
    kind: SoundKind
    label: str
    named: bool


NAMING_CASES = (
    NamingCase(HI_HAT, "HI-HAT: CLOSED", named=True),
    NamingCase(HI_HAT, "HI-HAT", named=True),
    NamingCase(BASS, "BASS: SLAP", named=True),
    NamingCase(BASS, "BASS DRUM", named=False),
    NamingCase(BASS_DRUM, "BASS: SYNTH", named=False),
    NamingCase(SNARE, "LO-FI, SNARE", named=True),
    NamingCase(LEAD, "SYNTH: PAD", named=False),
    NamingCase(LEAD, "SYNTH", named=False),
)


@pytest.mark.parametrize("case", NAMING_CASES)
def test_a_kind_is_named_by_its_tags_and_everything_under_them(case: NamingCase) -> None:
    assert case.kind.is_named_by(case.label) is case.named
