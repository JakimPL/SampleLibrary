from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplecore.naming import choose_dominant_name, sanitize_sample_name


@dataclass
class SanitizeCase:
    raw: str
    expected: str


SANITIZE_CASES = [
    SanitizeCase(raw="Kick_01", expected="kick_01"),
    SanitizeCase(raw="KICK!!! (loud)", expected="kick loud"),
    SanitizeCase(raw="  snare  drum  ", expected="snare drum"),
    SanitizeCase(raw="hi-hat", expected="hi-hat"),
    SanitizeCase(raw="###", expected=""),
]


@pytest.mark.parametrize("case", SANITIZE_CASES, ids=lambda case: case.raw)
def test_sanitize_sample_name_folds_to_a_limited_character_set(case: SanitizeCase) -> None:
    assert sanitize_sample_name(case.raw) == case.expected


def test_choose_dominant_name_picks_the_most_common_sanitized_name() -> None:
    assert choose_dominant_name(["kick", "KICK", "Kick", "snare"]) == "kick"


def test_choose_dominant_name_breaks_a_tie_alphabetically_not_by_length() -> None:
    assert choose_dominant_name(["a very long descriptive name", "b"]) == "a very long descriptive name"
    assert choose_dominant_name(["z", "a very long descriptive name"]) == "a very long descriptive name"


def test_choose_dominant_name_ignores_names_that_sanitize_to_empty() -> None:
    assert choose_dominant_name(["###", "kick"]) == "kick"


def test_choose_dominant_name_on_no_usable_names_returns_empty() -> None:
    assert choose_dominant_name(["", "   ", "###"]) == ""
