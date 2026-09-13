from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplecore.labeling.labels import (
    SampleLabel,
    format_path,
    label_agreement,
    written_paths,
)


@dataclass(frozen=True)
class ParseCase:
    text: str
    paths: frozenset[tuple[str, ...]]


@pytest.mark.parametrize(
    "case",
    [
        ParseCase("SNARE", frozenset({("SNARE",)})),
        ParseCase("HI-HAT: CLOSED, LO-FI", frozenset({("HI-HAT", "CLOSED"), ("LO-FI",)})),
        ParseCase("PIANO: ELECTRIC: RHODES", frozenset({("PIANO", "ELECTRIC", "RHODES")})),
        ParseCase("  synth ,pluck  ", frozenset({("SYNTH",), ("PLUCK",)})),
        ParseCase("SYNTH,, : ,PLUCK", frozenset({("SYNTH",), ("PLUCK",)})),
        ParseCase("", frozenset()),
    ],
    ids=lambda case: repr(case.text),
)
def test_a_label_reads_as_the_tag_paths_a_person_typed(case: ParseCase) -> None:
    assert SampleLabel.parse(case.text).paths == case.paths


def test_a_specification_asserts_every_category_above_it() -> None:
    label = SampleLabel.parse("PIANO: ELECTRIC: RHODES, LO-FI")

    assert label.closure == {("PIANO",), ("PIANO", "ELECTRIC"), ("PIANO", "ELECTRIC", "RHODES"), ("LO-FI",)}
    assert label.top_level == {"PIANO", "LO-FI"}


def test_the_same_name_under_two_categories_is_two_tags() -> None:
    assert SampleLabel.parse("BASS: ELECTRIC").paths.isdisjoint(SampleLabel.parse("GUITAR: ELECTRIC").paths)


def test_truncating_reads_a_label_at_a_coarser_level() -> None:
    label = SampleLabel.parse("HI-HAT: CLOSED, CYMBAL: CRASH, LO-FI")

    assert label.truncated(depth=1) == SampleLabel.parse("HI-HAT, CYMBAL, LO-FI")
    assert label.truncated(depth=2) == label


def test_truncating_keeps_at_least_one_level() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        SampleLabel.parse("SNARE").truncated(depth=0)


@dataclass(frozen=True)
class AgreementCase:
    first: str
    second: str
    agreement: float


@pytest.mark.parametrize(
    "case",
    [
        AgreementCase("HI-HAT: CLOSED", "HI-HAT: CLOSED", 1.0),
        AgreementCase("HI-HAT: CLOSED", "HI-HAT: OPEN", 1 / 3),
        AgreementCase("HI-HAT: CLOSED", "HI-HAT", 1 / 2),
        AgreementCase("SYNTH, PLUCK", "SYNTH: PULSE, CHIPTUNE", 1 / 4),
        AgreementCase("SNARE", "TOM", 0.0),
        AgreementCase("", "", 0.0),
    ],
    ids=lambda case: f"{case.first!r}~{case.second!r}",
)
def test_agreement_gives_graded_credit_along_the_hierarchy(case: AgreementCase) -> None:
    first = SampleLabel.parse(case.first)
    second = SampleLabel.parse(case.second)

    assert label_agreement(first, second) == pytest.approx(case.agreement)
    assert label_agreement(second, first) == pytest.approx(case.agreement)


def test_a_path_formats_the_way_a_person_writes_it() -> None:
    assert format_path(("PIANO", "ELECTRIC", "RHODES")) == "PIANO: ELECTRIC: RHODES"


def test_the_written_order_of_a_label_is_kept_and_a_repeated_tag_counted_once() -> None:
    assert written_paths("synth: pulse, chiptune, SYNTH: PULSE, , bass") == (
        ("SYNTH", "PULSE"),
        ("CHIPTUNE",),
        ("BASS",),
    )
