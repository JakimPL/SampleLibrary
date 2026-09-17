from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecloud.categories.vocabulary import (
    HAND_LABELS_CHOICE,
    INSTRUMENT_VOCABULARY,
    INSTRUMENTS_CHOICE,
    VocabularyRefused,
    prompt_for,
    read_vocabulary_file,
    vocabulary_from,
)
from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class PromptCase:
    label: str
    prompt: str


@pytest.mark.parametrize(
    "case",
    [
        PromptCase("BASS DRUM", "This is the sound of bass drum."),
        PromptCase("HI-HAT: CLOSED", "This is the sound of closed hi-hat."),
        PromptCase("bass: synth", "This is the sound of synth bass."),
    ],
    ids=lambda case: case.label,
)
def test_a_prompt_reads_the_label_from_its_specification_outward(case: PromptCase) -> None:
    assert prompt_for(case.label) == case.prompt


def test_the_shipped_vocabulary_is_the_default_choice(connection: Connection) -> None:
    assert vocabulary_from(INSTRUMENTS_CHOICE, connection) == INSTRUMENT_VOCABULARY


def test_a_file_names_one_label_per_line(tmp_path: Path, connection: Connection) -> None:
    listing = tmp_path / "labels.txt"
    listing.write_text("PIANO\n\n  STRINGS: PIZZICATO \n", encoding="utf-8")

    assert vocabulary_from(str(listing), connection) == ("PIANO", "STRINGS: PIZZICATO")


def test_a_file_passes_over_comments_and_names_each_label_once_in_its_canonical_spelling(tmp_path: Path) -> None:
    listing = tmp_path / "labels.txt"
    listing.write_text("# drums first\nhi-hat:closed\nSNARE\nHI-HAT: CLOSED\n  # pitched\nsnare\n", encoding="utf-8")

    assert read_vocabulary_file(listing) == ("HI-HAT: CLOSED", "SNARE")


@dataclass(frozen=True)
class RefusedFileCase:
    content: str | None
    reason: str


@pytest.mark.parametrize(
    "case",
    [
        RefusedFileCase(content="\n# nothing here\n", reason="holds no label"),
        RefusedFileCase(content="PIANO\nBASS, SYNTH\n", reason="line 2"),
        RefusedFileCase(content=None, reason="cannot be read"),
    ],
    ids=("no label", "two tags on one line", "a missing file"),
)
def test_a_file_that_is_no_list_of_labels_is_refused(case: RefusedFileCase, tmp_path: Path) -> None:
    listing = tmp_path / "labels.txt"
    if case.content is not None:
        listing.write_text(case.content, encoding="utf-8")

    with pytest.raises(VocabularyRefused, match=case.reason):
        read_vocabulary_file(listing)


def test_the_hand_label_vocabulary_holds_the_top_levels_and_their_specifications(connection: Connection) -> None:
    PostgresSampleAnnotationRepository(connection).upsert_many(
        (
            _annotation("a" * 64, "HI-HAT: CLOSED, LO-FI"),
            _annotation("b" * 64, "HI-HAT: OPEN: TIGHT"),
        )
    )

    assert set(vocabulary_from(HAND_LABELS_CHOICE, connection)) == {"HI-HAT", "HI-HAT: CLOSED", "HI-HAT: OPEN", "LO-FI"}


def _annotation(sample_hash: str, label: str) -> SampleAnnotation:
    return SampleAnnotation(
        label=label,
        rating=None,
        favorite=False,
        sample_hash=sample_hash,
        anchor=ModuleSlotAnchor(
            occurrence=SampleOccurrence(module_hash="c" * 64, instrument_index=0, sample_slot=0),
            module_filename="song.xm",
            sample_name="a sample",
        ),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )
