from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from pydantic import BaseModel, Field
from tqdm import tqdm

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_bytes_atomically

PROGRESS_FILE_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_PROGRESS_FILE"
REPORT_INTERVAL_SECONDS: Final[float] = 1.0


class ProgressReport(BaseModel):
    """How far one pass has come, as the program watching it reads it: what it counts, how many are done, of how many."""

    model_config = FROZEN

    label: str
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    updated_at: datetime


class ProgressBar:
    """One pass's count of finished work, drawn on the terminal and reported to a watching program.

    The pipeline names a file in `SAMPLELIBRARY_PROGRESS_FILE` for each step it runs, and the bar
    writes its count there at most once every `REPORT_INTERVAL_SECONDS`, and once more as it closes,
    so the application shows a step's progress while the terminal keeps its own bar.
    """

    def __init__(self, *, total: int, label: str) -> None:
        self._label = label
        self._total = total
        self._done = 0
        self._reported_at = -math.inf
        self._report_path = progress_file_from_environment()
        self._bar = tqdm(total=total, desc=label)

    def __enter__(self) -> Self:
        self._report()
        return self

    def __exit__(
        self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def update(self, count: int) -> None:
        """Record ``count`` further items as finished."""
        self._bar.update(count)
        self._done += count
        if time.monotonic() - self._reported_at >= REPORT_INTERVAL_SECONDS:
            self._report()

    def close(self) -> None:
        self._report()
        self._bar.close()

    def _report(self) -> None:
        self._reported_at = time.monotonic()
        if self._report_path is None:
            return
        report = ProgressReport(label=self._label, done=self._done, total=self._total, updated_at=datetime.now(UTC))
        write_bytes_atomically(self._report_path, report.model_dump_json().encode("utf-8"))


def tracked[T](items: Iterable[T], *, total: int, label: str) -> Iterator[T]:
    """Each of ``items`` in turn, counted on a `ProgressBar` as the caller finishes with it."""
    with ProgressBar(total=total, label=label) as bar:
        for item in items:
            yield item
            bar.update(1)


def progress_file_from_environment() -> Path | None:
    raw_path = os.environ.get(PROGRESS_FILE_ENVIRONMENT_VARIABLE)
    return Path(raw_path) if raw_path else None


def read_progress(path: Path) -> ProgressReport | None:
    """The last count a pass wrote to ``path``, where it wrote one."""
    if not path.is_file():
        return None
    return ProgressReport.model_validate_json(path.read_text(encoding="utf-8"))
