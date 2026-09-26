from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pytest

from samplecore.storage.staged_rows import CHECKPOINT_FILE_NAME, RowArray, StagedRows

IDENTITY: Final[str] = "a build"
ROW_COUNT: Final[int] = 4
VALUES: Final[str] = "values.npy"
ARRAYS: Final[tuple[RowArray, ...]] = (RowArray(VALUES, np.float32, (ROW_COUNT, 3)),)


def _two_rows_checkpointed(artifact: Path) -> None:
    rows = StagedRows.open(artifact, identity=IDENTITY, arrays=ARRAYS)
    rows.array(VALUES)[:2] = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    rows.advance_to(2)
    rows.checkpoint()


@dataclass(frozen=True)
class OtherBuildCase:
    """A build that differs from the one stopped, and so starts from an empty partial."""

    name: str
    identity: str
    arrays: tuple[RowArray, ...]


OTHER_BUILD_CASES: Final[tuple[OtherBuildCase, ...]] = (
    OtherBuildCase(name="another identity", identity="another build", arrays=ARRAYS),
    OtherBuildCase(name="other shapes", identity=IDENTITY, arrays=(RowArray(VALUES, np.float32, (ROW_COUNT + 1, 3)),)),
)


def test_a_build_of_the_same_identity_continues_after_the_last_checkpoint(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    _two_rows_checkpointed(artifact)

    rows = StagedRows.open(artifact, identity=IDENTITY, arrays=ARRAYS)

    assert rows.resumed_rows == 2
    np.testing.assert_array_equal(rows.array(VALUES)[:2], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def test_rows_written_after_the_last_checkpoint_are_written_again(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    _two_rows_checkpointed(artifact)
    rows = StagedRows.open(artifact, identity=IDENTITY, arrays=ARRAYS)
    rows.array(VALUES)[2] = [7.0, 8.0, 9.0]
    rows.advance_to(3)

    assert StagedRows.open(artifact, identity=IDENTITY, arrays=ARRAYS).resumed_rows == 2


@pytest.mark.parametrize("case", OTHER_BUILD_CASES, ids=lambda case: case.name)
def test_another_build_starts_from_an_empty_partial(tmp_path: Path, case: OtherBuildCase) -> None:
    artifact = tmp_path / "artifact"
    _two_rows_checkpointed(artifact)

    rows = StagedRows.open(artifact, identity=case.identity, arrays=case.arrays)

    assert rows.resumed_rows == 0
    assert not rows.array(VALUES).any()


def test_a_completed_build_leaves_its_arrays_and_no_count(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    rows = StagedRows.open(artifact, identity=IDENTITY, arrays=ARRAYS)
    rows.array(VALUES)[:] = 1.0
    rows.advance_to(ROW_COUNT)
    rows.checkpoint()

    staging = rows.complete()

    assert sorted(path.name for path in staging.iterdir()) == [VALUES]
    assert not (staging / CHECKPOINT_FILE_NAME).exists()
    np.testing.assert_array_equal(np.load(staging / VALUES), np.ones((ROW_COUNT, 3)))
