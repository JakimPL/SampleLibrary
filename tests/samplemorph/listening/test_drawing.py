from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pytest
from sqlalchemy import Connection

from samplecore.storage.sample_audio import SampleAudio
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.listening.candidates import NoScoringShown
from samplemorph.listening.drawing import SHORTEST_RETUNING_SEMITONES, draw_pairs
from samplemorph.listening.pairs import CatalogPair, PairSet, RetunedPair
from tests.samplemorph.listening.conftest import CatalogedTone, seed_labeled_tones

SEED: Final[int] = 7
PIANO: Final[str] = "PIANO"
PAD: Final[str] = "SYNTH: PAD"
SNARE: Final[str] = "SNARE"
CHORD: Final[str] = "CHORD"
HAND_LABELED_PIANO_COUNT: Final[int] = 6
LOW_PAD_COUNT: Final[int] = 6
TONES: Final[tuple[CatalogedTone, ...]] = (
    *(
        CatalogedTone(suggested_label=CHORD, score=0.1, module_index=index, hand_label=PIANO)
        for index in range(HAND_LABELED_PIANO_COUNT)
    ),
    CatalogedTone(suggested_label=PIANO, score=0.9, module_index=10, hand_label=SNARE),
    CatalogedTone(suggested_label=PAD, score=0.9, module_index=11, hand_label=None),
    CatalogedTone(suggested_label=PAD, score=0.8, module_index=11, hand_label=None),
    *(
        CatalogedTone(suggested_label=PAD, score=0.2, module_index=20 + index, hand_label=None)
        for index in range(LOW_PAD_COUNT)
    ),
)
RELABELED_INDEX: Final[int] = HAND_LABELED_PIANO_COUNT
TOP_PAD_INDICES: Final[tuple[int, int]] = (HAND_LABELED_PIANO_COUNT + 1, HAND_LABELED_PIANO_COUNT + 2)


@pytest.fixture
def drawn(connection: Connection, tmp_path: Path) -> tuple[PairSet, tuple[str, ...]]:
    hashes = seed_labeled_tones(connection, tmp_path, TONES)
    return draw_pairs(connection, SampleAudio.from_catalog(connection, tmp_path), random_seed=SEED), hashes


def _drawn_hashes(pair_set: PairSet) -> list[str]:
    hashes = []
    for pair in pair_set.pairs:
        match pair:
            case CatalogPair():
                hashes.extend((pair.first.sample_hash, pair.second.sample_hash))
            case RetunedPair():
                hashes.append(pair.sample.sample_hash)
    return hashes


def test_a_draw_repeats_for_the_same_seed(
    drawn: tuple[PairSet, tuple[str, ...]], connection: Connection, tmp_path: Path
) -> None:
    pair_set, _ = drawn

    again = draw_pairs(connection, SampleAudio.from_catalog(connection, tmp_path), random_seed=SEED)

    assert again == pair_set


def test_no_sample_is_drawn_twice(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    hashes = _drawn_hashes(drawn[0])

    assert hashes
    assert len(hashes) == len(set(hashes))


def test_a_hand_label_decides_the_kind_a_sample_is_drawn_as(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    pair_set, hashes = drawn
    relabeled = hashes[RELABELED_INDEX]

    labels = [
        end.label
        for pair in pair_set.pairs
        if isinstance(pair, CatalogPair)
        for end in (pair.first, pair.second)
        if end.sample_hash == relabeled
    ]

    assert labels in ([], [SNARE])


def test_two_samples_of_one_module_are_never_paired(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    pair_set, hashes = drawn
    one_module = {hashes[index] for index in TOP_PAD_INDICES}

    paired = [
        {pair.first.sample_hash, pair.second.sample_hash} for pair in pair_set.pairs if isinstance(pair, CatalogPair)
    ]

    assert one_module not in paired


def test_pairs_of_each_kind_and_across_kinds_are_drawn(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    names = [pair.name.split("-", 1)[1] for pair in drawn[0].pairs]

    assert names.count("same-piano") == 2
    assert "cross-piano-pad" in names


def test_a_suggestion_scored_below_its_labels_top_quarter_is_left_out(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    pair_set, hashes = drawn
    top_pads = {hashes[index] for index in TOP_PAD_INDICES}

    pad_hashes = {
        end.sample_hash
        for pair in pair_set.pairs
        if isinstance(pair, CatalogPair)
        for end in (pair.first, pair.second)
        if end.label == PAD
    }

    assert pad_hashes
    assert pad_hashes <= top_pads


def test_a_retuned_pair_lies_a_fifth_to_an_octave_apart(drawn: tuple[PairSet, tuple[str, ...]]) -> None:
    retuned = [pair for pair in drawn[0].pairs if isinstance(pair, RetunedPair)]

    assert retuned
    for pair in retuned:
        interval = SEMITONES_PER_OCTAVE * np.log2(pair.second_rate_hz / pair.first_rate_hz)
        assert SHORTEST_RETUNING_SEMITONES - 1e-9 <= interval <= SEMITONES_PER_OCTAVE + 1e-9


def test_a_catalog_showing_no_scoring_is_refused(connection: Connection, tmp_path: Path) -> None:
    with pytest.raises(NoScoringShown):
        draw_pairs(connection, SampleAudio.from_catalog(connection, tmp_path), random_seed=SEED)
