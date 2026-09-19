from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from samplemorph.measurement.pitch.reading import STORED_VARIANT, SampleReadings, Variant
from samplemorph.measurement.pitch.trials import TrialKind

FIRST_REFEREE: Final[str] = "first-referee"
SECOND_REFEREE: Final[str] = "second-referee"
REFEREES: Final[tuple[str, str]] = (FIRST_REFEREE, SECOND_REFEREE)
VARIANTS: Final[tuple[Variant, ...]] = (
    Variant(name="retuned+5", kind=TrialKind.RETUNING, expected_semitones=5.0),
    Variant(name="retuned-12", kind=TrialKind.RETUNING, expected_semitones=-12.0),
    Variant(name="quieter", kind=TrialKind.INVARIANCE, expected_semitones=0.0),
)


@dataclass(frozen=True)
class Reading:
    """A stand-in reader's answer."""

    semitones: float
    reliability: float


def truthful_sample(sample_hash: str, *, stored_semitones: float, seconds: float, sound_type: str) -> SampleReadings:
    """A held-out sample both referees read where it is, and every variant where the variant moves it."""
    readings: dict[tuple[str, str], Reading | None] = {}
    for referee in REFEREES:
        readings[(STORED_VARIANT, referee)] = Reading(semitones=stored_semitones, reliability=0.9)
        for variant in VARIANTS:
            readings[(variant.name, referee)] = Reading(
                semitones=stored_semitones + variant.expected_semitones, reliability=0.8
            )
    return SampleReadings(sample_hash=sample_hash, seconds=seconds, sound_type=sound_type, readings=readings)
