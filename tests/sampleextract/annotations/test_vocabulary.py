from __future__ import annotations

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.vocabulary import LabelVocabulary
from sampleextract.annotations.vocabulary import vocabulary_lines


def test_the_tree_indents_each_specification_under_its_category() -> None:
    vocabulary = LabelVocabulary.from_labels(
        SampleLabel.parse(text) for text in ("PIANO: ELECTRIC: RHODES", "PIANO", "BASS: ELECTRIC")
    )

    lines = vocabulary_lines(vocabulary)

    assert lines[:5] == (
        "    2  PIANO",
        "        1  ELECTRIC",
        "            1  RHODES",
        "    1  BASS",
        "        1  ELECTRIC",
    )
    assert all("Used both as a category" not in line for line in lines)


def test_an_empty_vocabulary_renders_nothing() -> None:
    assert vocabulary_lines(LabelVocabulary.from_labels(())) == ()
