from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from samplemorph.measurement.ladders.session import (
    LADDERS_FILE_NAME,
    PAIR_SUMMARY_FILE_NAME,
    PAIRS_FILE_NAME,
    PICTURES_DIRECTORY_NAME,
    SUMMARY_FILE_NAME,
    read_ladders,
)
from samplemorph.measurement.ladders.truth import Ladder, LadderFamily, UnrelatedPair
from samplemorph.measurement.ladders.walkers import CrossfadeWalker, LadderWalker, LatentWalker, TranslationOracle
from tests.samplemorph.measurement.ladders.conftest import AXIS, WEIGHTS

WALKERS: tuple[LadderWalker, ...] = (CrossfadeWalker(), TranslationOracle(bands_per_semitone=AXIS.bands_per_semitone))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _still(ladder: Ladder) -> Ladder:
    return Ladder(
        family=ladder.family,
        name="still",
        interval_semitones=ladder.interval_semitones,
        weights=ladder.weights,
        truth=np.repeat(ladder.truth[:1], len(ladder.weights), axis=0),
    )


def test_every_ladder_and_pair_is_read_by_every_walker_that_has_a_path_for_it(retuned: Ladder, tmp_path: Path) -> None:
    pair = UnrelatedPair(name="pair", weights=WEIGHTS, ends=np.stack([retuned.truth[0], retuned.truth[-1]]))

    summary = read_ladders((retuned, _still(retuned)), (pair,), walkers=WALKERS, axis=AXIS, output_directory=tmp_path)

    assert (summary.ladder_count, summary.pair_count, summary.skipped_count) == (1, 1, 1)
    ladders = _rows(tmp_path / LADDERS_FILE_NAME)
    assert {row["model"] for row in ladders} == {walker.name for walker in WALKERS}
    assert len(ladders) == len(WALKERS) * (len(WEIGHTS) - 2)
    assert [row["model"] for row in _rows(tmp_path / SUMMARY_FILE_NAME)] == ["crossfade", "oracle"]
    assert {row["model"] for row in _rows(tmp_path / PAIRS_FILE_NAME)} == {"crossfade"}
    assert len(_rows(tmp_path / PAIR_SUMMARY_FILE_NAME)) == 1
    pictures = tmp_path / PICTURES_DIRECTORY_NAME
    assert (pictures / LadderFamily.RETUNED.value / "tone.png").is_file()
    assert (pictures / LadderFamily.UNRELATED.value / "pair.png").is_file()
    assert not (pictures / LadderFamily.RETUNED.value / "still.png").exists()


def test_a_reading_with_nothing_far_enough_apart_to_read_is_refused(retuned: Ladder, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="too close"):
        read_ladders((_still(retuned),), (), walkers=WALKERS, axis=AXIS, output_directory=tmp_path)


class _QuietCritic:
    def score(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.zeros(len(grids), dtype=np.float32)


class _FlatteningAutoencoder:
    def encode(self, grids: NDArray[np.float32]) -> NDArray[np.float32]:
        return grids.reshape(grids.shape[0], -1)

    def decode(self, latents: NDArray[np.float32]) -> NDArray[np.float32]:
        return latents.reshape(latents.shape[0], AXIS.band_count, -1)


def test_the_critic_s_columns_are_filled_for_a_walker_with_a_critic_and_left_empty_for_the_rest(
    retuned: Ladder, tmp_path: Path
) -> None:
    walkers = (
        CrossfadeWalker(),
        LatentWalker(name="flat", autoencoder=_FlatteningAutoencoder(), critic=_QuietCritic()),
    )

    read_ladders((retuned,), (), walkers=walkers, axis=AXIS, output_directory=tmp_path)

    summary = {row["model"]: row for row in _rows(tmp_path / SUMMARY_FILE_NAME)}
    assert summary["crossfade"]["critic_path"] == ""
    assert float(summary["flat"]["critic_path"]) == 0.0
    assert {row["critic_crossfade"] for row in _rows(tmp_path / LADDERS_FILE_NAME) if row["model"] == "flat"} == {"0.0"}


def test_the_summary_keeps_the_median_moved_share_apart_from_the_share_of_steps_read_as_moved(
    retuned: Ladder, tmp_path: Path
) -> None:
    read_ladders((retuned,), (), walkers=WALKERS, axis=AXIS, output_directory=tmp_path)

    oracle = next(row for row in _rows(tmp_path / SUMMARY_FILE_NAME) if row["model"] == "oracle")

    assert float(oracle["verdict_moved"]) == 1.0
    assert 0.5 < float(oracle["moved_share"]) < 1.0
