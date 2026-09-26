from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_bytes_atomically
from samplecore.storage.staging import fresh_staging, partial_path

CHECKPOINT_FILE_NAME: Final[str] = "checkpoint.json"
CHECKPOINT_SECONDS: Final[float] = 10.0


@dataclass(frozen=True)
class RowArray:
    """One array a build fills row by row: the file it is kept in, its element type, and its shape, rows first."""

    file_name: str
    dtype: type[np.generic]
    shape: tuple[int, ...]


class RowCheckpoint(BaseModel):
    """What a stopped build left in its partial: which build it was, and how many of its rows stand finished."""

    model_config = FROZEN

    identity: str
    finished_rows: int = Field(ge=0)


class StagedRows:
    """Memory-mapped arrays a build fills in order inside its partial, and the count of rows that stand finished.

    A build opens them with `open`, writes each row as it arrives, and reports its position with
    `advance_to`; every `CHECKPOINT_SECONDS` the arrays are flushed to disk and only then is the
    count written, so the count never runs ahead of the rows on disk, whether the build is
    interrupted, killed or the machine loses power. A later build of the same `identity` opens the
    same rows and continues after the last count; anything else starts from an empty partial.
    """

    def __init__(self, staging: Path, *, identity: str, arrays: Mapping[str, np.memmap], finished_rows: int) -> None:
        self._staging = staging
        self._identity = identity
        self._arrays = arrays
        self._resumed_rows = finished_rows
        self._finished_rows = finished_rows
        self._checkpointed_at = time.monotonic()

    @classmethod
    def open(cls, artifact: Path, *, identity: str, arrays: tuple[RowArray, ...]) -> StagedRows:
        """The rows a build of `artifact` fills, continuing a stopped build of the same `identity` where one stands."""
        staging = partial_path(artifact)
        finished_rows = _finished_rows(staging, identity=identity, arrays=arrays)
        if finished_rows is None:
            staging = fresh_staging(artifact)
            maps = {
                array.file_name: np.lib.format.open_memmap(
                    staging / array.file_name, mode="w+", dtype=array.dtype, shape=array.shape
                )
                for array in arrays
            }
            return cls(staging, identity=identity, arrays=maps, finished_rows=0)
        maps = {array.file_name: np.lib.format.open_memmap(staging / array.file_name, mode="r+") for array in arrays}
        return cls(staging, identity=identity, arrays=maps, finished_rows=finished_rows)

    @property
    def staging(self) -> Path:
        return self._staging

    @property
    def resumed_rows(self) -> int:
        """How many rows a stopped build had finished when this one opened them."""
        return self._resumed_rows

    def array(self, file_name: str) -> np.memmap:
        return self._arrays[file_name]

    def advance_to(self, finished_rows: int) -> None:
        """Record that every row before `finished_rows` is written, checkpointing once a checkpoint is due."""
        self._finished_rows = finished_rows
        if time.monotonic() - self._checkpointed_at >= CHECKPOINT_SECONDS:
            self.checkpoint()

    def checkpoint(self) -> None:
        """Flush every array to disk, then record how many rows stand finished."""
        for array in self._arrays.values():
            array.flush()
        checkpoint = RowCheckpoint(identity=self._identity, finished_rows=self._finished_rows)
        write_bytes_atomically(self._staging / CHECKPOINT_FILE_NAME, checkpoint.model_dump_json().encode("utf-8"))
        self._checkpointed_at = time.monotonic()

    def complete(self) -> Path:
        """Flush the finished arrays and drop the count, leaving the partial holding the build alone, ready to publish."""
        for array in self._arrays.values():
            array.flush()
        self._arrays = {}
        (self._staging / CHECKPOINT_FILE_NAME).unlink(missing_ok=True)
        return self._staging


def _finished_rows(staging: Path, *, identity: str, arrays: tuple[RowArray, ...]) -> int | None:
    """How many rows a stopped build of this `identity` finished in `staging`, where its arrays stand as it left them."""
    checkpoint_path = staging / CHECKPOINT_FILE_NAME
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = RowCheckpoint.model_validate_json(checkpoint_path.read_text(encoding="utf-8"))
    except ValidationError:
        return None
    if checkpoint.identity != identity or not all(_stands(staging / array.file_name, array) for array in arrays):
        return None
    return checkpoint.finished_rows


def _stands(path: Path, array: RowArray) -> bool:
    if not path.is_file():
        return False
    try:
        held = np.load(path, mmap_mode="r")
    except (ValueError, OSError):
        return False
    return tuple(held.shape) == array.shape and held.dtype == np.dtype(array.dtype)
