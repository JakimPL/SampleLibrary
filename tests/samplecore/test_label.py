from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from samplecore.models.label import LabelSource, SampleLabel
from samplecore.models.sample_properties import SampleOccurrence


def _label(text: str, *, sample_hash: str) -> SampleLabel:
    return SampleLabel(
        sample_hash=sample_hash,
        label=text,
        occurrence=SampleOccurrence(module_hash=format(1, "064x"), instrument_index=0, sample_slot=0),
        module_filename="song.it",
        sample_name="smp01",
        source=LabelSource.SAMPLE,
        labeled_at=datetime.now(UTC),
    )


def test_a_label_keeps_whatever_wording_was_chosen(sample_hash_a: str) -> None:
    assert _label("dirty 909 kick", sample_hash=sample_hash_a).label == "dirty 909 kick"


def test_surrounding_whitespace_is_trimmed_so_one_wording_stays_one_label(sample_hash_a: str) -> None:
    assert _label("  bass  ", sample_hash=sample_hash_a).label == "bass"


@pytest.mark.parametrize("text", ["", "   "])
def test_a_label_saying_nothing_is_rejected(text: str, sample_hash_a: str) -> None:
    with pytest.raises(ValidationError):
        _label(text, sample_hash=sample_hash_a)


def test_a_label_records_which_gesture_applied_it(sample_hash_a: str) -> None:
    """A label inherited from a group is weaker evidence than one chosen for a single sample."""
    grouped = _label("snare", sample_hash=sample_hash_a).model_copy(update={"source": LabelSource.EQUIVALENCE_CLASS})

    assert grouped.source is LabelSource.EQUIVALENCE_CLASS
