from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.vocabulary import LabelVocabulary, TagUsage, read_vocabulary
from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository

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


def _annotation(label: str | None, *, days_ago: int, sample_hash: str) -> SampleAnnotation:
    return SampleAnnotation(
        label=label,
        rating=None if label is not None else 3,
        favorite=False,
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0),
        module_filename="song.xm",
        sample_name="a sample",
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


def test_the_vocabulary_is_read_from_every_labeled_annotation(connection: Connection) -> None:
    """A rating without a label names no tag, and a specification counts toward its category."""
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            _annotation("HI-HAT: CLOSED", days_ago=1, sample_hash="a" * 64),
            _annotation("HI-HAT: OPEN, LO-FI", days_ago=2, sample_hash="b" * 64),
            _annotation(None, days_ago=3, sample_hash="c" * 64),
        )
    )

    vocabulary = read_vocabulary(connection)

    assert vocabulary.top_level == (
        TagUsage(path=("HI-HAT",), sample_count=2),
        TagUsage(path=("LO-FI",), sample_count=1),
    )
