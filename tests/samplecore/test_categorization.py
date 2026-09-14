from __future__ import annotations

from dataclasses import dataclass

import pytest

from samplecore.categorization import classify_sample_category, classify_sample_names
from samplecore.models.category import SampleCategory
from samplecore.naming import NO_SAMPLE_NAMES, SampleNames


@dataclass
class ClassificationCase:
    names: tuple[str, ...]
    expected: SampleCategory


CLASSIFICATION_CASES = [
    ClassificationCase(names=("Kick_01",), expected=SampleCategory.KICK),
    ClassificationCase(names=("BASSDRUM",), expected=SampleCategory.KICK),
    ClassificationCase(names=("bd 909",), expected=SampleCategory.KICK),
    ClassificationCase(names=("snare rim",), expected=SampleCategory.SNARE),
    ClassificationCase(names=("Clap-808",), expected=SampleCategory.CLAP),
    ClassificationCase(names=("hi-hat closed",), expected=SampleCategory.HI_HAT),
    ClassificationCase(names=("open hh",), expected=SampleCategory.HI_HAT),
    ClassificationCase(names=("crash cymbal",), expected=SampleCategory.CYMBAL),
    ClassificationCase(names=("ride bell",), expected=SampleCategory.CYMBAL),
    ClassificationCase(names=("floor tom",), expected=SampleCategory.PERCUSSION),
    ClassificationCase(names=("conga hi",), expected=SampleCategory.PERCUSSION),
    ClassificationCase(names=("Sub Bass",), expected=SampleCategory.BASS),
    ClassificationCase(names=("808 bass",), expected=SampleCategory.BASS),
    ClassificationCase(names=("lead arp",), expected=SampleCategory.LEAD),
    ClassificationCase(names=("ambient pad",), expected=SampleCategory.PAD),
    ClassificationCase(names=("pluck stab",), expected=SampleCategory.PLUCK),
    ClassificationCase(names=("vox chant",), expected=SampleCategory.VOCAL),
    ClassificationCase(names=("riser fx",), expected=SampleCategory.FX),
    ClassificationCase(names=("break loop",), expected=SampleCategory.LOOP),
    ClassificationCase(names=("untitled",), expected=SampleCategory.UNCATEGORIZED),
    ClassificationCase(names=(), expected=SampleCategory.UNCATEGORIZED),
]


@pytest.mark.parametrize(
    "case", CLASSIFICATION_CASES, ids=lambda case: case.expected.value + "-" + "-".join(case.names)
)
def test_classify_sample_category_matches_the_expected_keyword_group(case: ClassificationCase) -> None:
    assert classify_sample_category(case.names) == case.expected


def test_classify_sample_category_checks_every_occurrence_name_not_only_the_first() -> None:
    assert classify_sample_category(("untitled", "kick 02")) == SampleCategory.KICK


def test_classify_sample_category_resolves_a_bass_drum_name_to_kick_not_bass() -> None:
    assert classify_sample_category(("bassdrum heavy",)) == SampleCategory.KICK


@dataclass(frozen=True)
class FolderFallbackCase:
    names: SampleNames
    expected: SampleCategory


@pytest.mark.parametrize(
    "case",
    [
        FolderFallbackCase(
            names=SampleNames(own_names=("Snare 01",), instrument_names=(), folder_names=("Kicks",)),
            expected=SampleCategory.SNARE,
        ),
        FolderFallbackCase(
            names=SampleNames(own_names=("VEH1 001",), instrument_names=(), folder_names=("Kicks", "Club Pack")),
            expected=SampleCategory.KICK,
        ),
        FolderFallbackCase(
            names=SampleNames(own_names=("001",), instrument_names=(), folder_names=("Claps", "Subdued Loops")),
            expected=SampleCategory.CLAP,
        ),
        FolderFallbackCase(
            names=SampleNames(own_names=("smp03",), instrument_names=("warm pad",), folder_names=("Kicks",)),
            expected=SampleCategory.PAD,
        ),
        FolderFallbackCase(names=NO_SAMPLE_NAMES, expected=SampleCategory.UNCATEGORIZED),
    ],
    ids=(
        "a name outranks its folder",
        "a folder names an unnamed sound",
        "the nearest folder outranks the one above",
        "an instrument outranks a folder",
        "nothing to go by",
    ),
)
def test_folders_categorize_only_what_the_names_leave_uncategorized(case: FolderFallbackCase) -> None:
    assert classify_sample_names(case.names) == case.expected
