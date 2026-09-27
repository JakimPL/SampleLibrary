from __future__ import annotations

import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from samplecore.ports import MAXIMUM_PORT, MINIMUM_PORT
from samplecore.storage.atomic import write_bytes_atomically
from samplelibrary.app.instance.processes import ProcessIdentity

WRITE_ATTEMPTS: Final[int] = 20
WRITE_RETRY_SECONDS: Final[float] = 0.05


class InstanceRecord(BaseModel):
    """Where the application running under one config listens, and which process it is.

    The record stays after the application ends, so the next start listens on the same port and
    the browser keeps what it stores for that address. Every later version reads it, so the model
    reads past fields it does not know.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    host: str
    port: int = Field(ge=MINIMUM_PORT, le=MAXIMUM_PORT)
    process: ProcessIdentity

    @property
    def address(self) -> str:
        """The address a browser on this machine opens the application at."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/"


def read_record(path: Path) -> InstanceRecord | None:
    """The record at ``path``, or None where none can be read: missing, being replaced, or written by something else."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    try:
        return InstanceRecord.model_validate_json(content)
    except ValidationError:
        return None


def write_record(path: Path, record: InstanceRecord) -> None:
    """Put the record in place whole.

    On Windows a file another process has open cannot be replaced, so a start reading the record
    at that moment makes the write wait a little and try again.
    """
    content = record.model_dump_json().encode("utf-8")
    for _ in range(WRITE_ATTEMPTS - 1):
        try:
            write_bytes_atomically(path, content)
            return
        except PermissionError:
            time.sleep(WRITE_RETRY_SECONDS)
    write_bytes_atomically(path, content)
