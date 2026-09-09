from __future__ import annotations

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.vocabulary import LabelVocabulary, TagUsage

LABELS = (
    "HI-HAT: CLOSED, LO-FI",
    "HI-HAT: CLOSED",
    "HI-HAT: OPEN",
    "BASS: ELECTRIC",
    "BASS, ELECTRIC",
    "SNARE, LO-FI",
)


def _vocabulary() -> LabelVocabulary:
    return LabelVocabulary.from_labels(SampleLabel.parse(text) for text in LABELS)


def test_a_category_counts_every_sample_labeled_with_a_specification_of_it() -> None:
    vocabulary = _vocabulary()

    assert vocabulary.top_level[0] == TagUsage(path=("HI-HAT",), sample_count=3)
    assert vocabulary.children(("HI-HAT",)) == (
        TagUsage(path=("HI-HAT", "CLOSED"), sample_count=2),
        TagUsage(path=("HI-HAT", "OPEN"), sample_count=1),
    )


def test_the_most_used_tag_comes_first_and_ties_read_alphabetically() -> None:
    counts = [(usage.path, usage.sample_count) for usage in _vocabulary().top_level]

    assert counts == [
        (("HI-HAT",), 3),
        (("BASS",), 2),
        (("LO-FI",), 2),
        (("ELECTRIC",), 1),
        (("SNARE",), 1),
    ]


def test_a_name_standing_alone_and_under_another_category_is_surfaced() -> None:
    assert _vocabulary().names_used_at_two_depths == ("ELECTRIC",)


def test_tags_carried_by_one_sample_are_listed() -> None:
    assert set(_vocabulary().singletons) == {("HI-HAT", "OPEN"), ("BASS", "ELECTRIC"), ("ELECTRIC",), ("SNARE",)}


def test_an_empty_vocabulary_has_no_findings() -> None:
    vocabulary = LabelVocabulary.from_labels(())

    assert vocabulary.usages == ()
    assert vocabulary.names_used_at_two_depths == ()
    assert vocabulary.singletons == ()
