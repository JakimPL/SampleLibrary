from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from samplecore.models.annotation import (
    NO_DECISIONS,
    AnnotationChanges,
    AnnotationDecision,
    AnnotationDecisions,
    AnnotationSource,
    ModuleSlotAnchor,
    SampleAnnotation,
)
from samplecore.models.sample_properties import SampleOccurrence


def _annotation(
    *,
    sample_hash: str,
    label: str | None = None,
    rating: int | None = None,
    favorite: bool = False,
) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=label,
        rating=rating,
        favorite=favorite,
        anchor=ModuleSlotAnchor(
            occurrence=SampleOccurrence(module_hash=format(1, "064x"), instrument_index=0, sample_slot=0),
            module_filename="song.it",
            sample_name="smp01",
        ),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )


def test_a_label_keeps_whatever_wording_was_chosen(sample_hash_a: str) -> None:
    assert _annotation(sample_hash=sample_hash_a, label="dirty 909 kick").label == "DIRTY 909 KICK"


def test_a_label_is_kept_in_one_case_however_it_was_typed(sample_hash_a: str) -> None:
    """One wording is one label: the case a person happened to type in never splits it in two."""
    assert _annotation(sample_hash=sample_hash_a, label="Warm Pad").label == "WARM PAD"


def test_surrounding_whitespace_is_trimmed_so_one_wording_stays_one_label(sample_hash_a: str) -> None:
    assert _annotation(sample_hash=sample_hash_a, label="  bass  ").label == "BASS"


@pytest.mark.parametrize("text", ["", "   "])
def test_a_label_saying_nothing_is_rejected(text: str, sample_hash_a: str) -> None:
    with pytest.raises(ValidationError):
        _annotation(sample_hash=sample_hash_a, label=text)


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_a_rating_outside_the_scale_is_rejected(rating: int, sample_hash_a: str) -> None:
    with pytest.raises(ValidationError):
        _annotation(sample_hash=sample_hash_a, rating=rating)


@pytest.mark.parametrize(
    "decision",
    [
        {"label": "hat"},
        {"rating": 4},
        {"favorite": True},
        {"label": "hat", "rating": 4, "favorite": True},
    ],
)
def test_any_one_decision_is_enough_for_an_annotation_to_exist(decision: dict[str, object], sample_hash_a: str) -> None:
    assert _annotation(sample_hash=sample_hash_a, **decision) is not None  # type: ignore[arg-type]


def test_an_annotation_recording_nothing_is_rejected(sample_hash_a: str) -> None:
    """A row earns its place by saying something; taking back the last decision removes it instead."""
    with pytest.raises(ValidationError):
        _annotation(sample_hash=sample_hash_a)


def test_an_annotation_records_which_gesture_applied_it(sample_hash_a: str) -> None:
    """A decision inherited from a group is weaker evidence than one made for a single sample."""
    grouped = _annotation(sample_hash=sample_hash_a, label="snare").model_copy(
        update={"source": AnnotationSource.EQUIVALENCE_CLASS}
    )

    assert grouped.source is AnnotationSource.EQUIVALENCE_CLASS


CURRENT = AnnotationDecisions(label="KICK", rating=4, favorite=True)


@dataclass(frozen=True)
class ChangeCase:
    values: AnnotationDecisions
    changed: frozenset[AnnotationDecision]
    expected: AnnotationDecisions


@pytest.mark.parametrize(
    "case",
    [
        ChangeCase(
            values=AnnotationDecisions(label=None, rating=2, favorite=False),
            changed=frozenset({AnnotationDecision.RATING}),
            expected=AnnotationDecisions(label="KICK", rating=2, favorite=True),
        ),
        ChangeCase(
            values=AnnotationDecisions(label="SNARE", rating=None, favorite=False),
            changed=frozenset({AnnotationDecision.LABEL}),
            expected=AnnotationDecisions(label="SNARE", rating=4, favorite=True),
        ),
        ChangeCase(
            values=NO_DECISIONS,
            changed=frozenset({AnnotationDecision.FAVORITE, AnnotationDecision.RATING}),
            expected=AnnotationDecisions(label="KICK", rating=None, favorite=False),
        ),
        ChangeCase(values=NO_DECISIONS, changed=frozenset(AnnotationDecision), expected=NO_DECISIONS),
    ],
    ids=("a rating alone", "a label alone", "clearing two", "clearing all three"),
)
def test_a_change_replaces_the_decisions_it_names_and_keeps_the_rest(case: ChangeCase) -> None:
    changes = AnnotationChanges(values=case.values, changed=case.changed)

    assert changes.applied_to(CURRENT) == case.expected


def test_a_label_is_stored_in_its_one_spelling(sample_hash_a: str) -> None:
    assert _annotation(sample_hash=sample_hash_a, label="hi-hat:closed,lo-fi").label == "HI-HAT: CLOSED, LO-FI"
