from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Final

import numpy as np
from pydantic import ConfigDict, TypeAdapter, ValidationError

from samplecore.storage.atomic import write_bytes_atomically
from samplecore.storage.staged_rows import RowArray, StagedRows
from samplecore.storage.staging import fresh_staging, partial_path

IDENTITY_FILE_NAME: Final[str] = "identity.txt"
STAGE_SUFFIX: Final[str] = ".json"
PROBES_NAME: Final[str] = "probes"
QUERIES_FILE_NAME: Final[str] = "queries.npy"
PROBE_STATUS_FILE_NAME: Final[str] = "status.npy"
# A score a metric could not read is NaN, which a stage keeps as it is.
STAGE_JSON: Final[ConfigDict] = {"ser_json_inf_nan": "constants"}


class EvaluationStages:
    """The finished stages of one evaluation, kept in the partial beside its report so a stopped pass takes up after them.

    The stages are named by `identity`, the digest of the experiment, the corpus and the settings a
    pass scores, so stages another pass left are cleared and this one starts over. A metric's result
    is kept whole once computed, and the retuned probes' vectors row by row as they are described.
    """

    def __init__(self, directory: Path, *, identity: str) -> None:
        self._directory = directory
        self._identity = identity

    @classmethod
    def open(cls, report_path: Path, *, identity: str) -> EvaluationStages:
        """The stages of the pass writing `report_path`, starting afresh where another pass's stand there."""
        directory = partial_path(report_path)
        identity_path = directory / IDENTITY_FILE_NAME
        if not identity_path.is_file() or identity_path.read_text(encoding="utf-8") != identity:
            directory = fresh_staging(report_path)
            write_bytes_atomically(identity_path, identity.encode("utf-8"))
        return cls(directory, identity=identity)

    def kept[Result](self, name: str, adapter: TypeAdapter[Result], compute: Callable[[], Result]) -> Result:
        """A metric's result: the one kept under `name` where one stands, or `compute`'s, kept whole before it returns."""
        path = self._directory / f"{name}{STAGE_SUFFIX}"
        if path.is_file():
            try:
                return adapter.validate_json(path.read_bytes())
            except ValidationError:
                path.unlink()
        result = compute()
        write_bytes_atomically(path, adapter.dump_json(result))
        return result

    def probe_rows(self, *, probe_count: int, offset_count: int, dimensions: int) -> StagedRows:
        """The retuned probes' rows: every offset's vector for each probe, and how its reading went."""
        return StagedRows.open(
            self._directory / PROBES_NAME,
            identity=self._identity,
            arrays=(
                RowArray(QUERIES_FILE_NAME, np.float64, (probe_count, offset_count, dimensions)),
                RowArray(PROBE_STATUS_FILE_NAME, np.uint8, (probe_count,)),
            ),
        )


def clear_stages(report_path: Path) -> None:
    """Remove the stages a pass kept beside `report_path`, once the report stands in their place."""
    shutil.rmtree(partial_path(report_path), ignore_errors=True)
