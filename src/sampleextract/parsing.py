from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from trackmod.core.songs.song import Song
from trackmod.trackers.it.module import ITModule
from trackmod.trackers.mod.module import MODModule
from trackmod.trackers.s3m.module import S3MModule
from trackmod.trackers.xm.module import XMModule

from samplecore.models.tracker import TrackerFormat

RECOVERABLE_PARSE_ERRORS: Final[tuple[type[Exception], ...]] = (ValueError, OSError, struct.error, IndexError)
# ValueError: TrackMod's own documented parse failures (a bad tag, a malformed structure) and every
#   pydantic ValidationError, which subclasses it. OSError: the file could not be read. struct.error and
#   IndexError: raw struct/array bounds failures a sufficiently corrupt file can still trigger beneath
#   TrackMod's own ValueError guards. Anything outside this set is treated as a bug, and crashes loudly.


@dataclass(frozen=True)
class ExtractionFailure:
    """One module a pass could not read, and why."""

    path: Path
    reason: str


def parse_module(data: bytes, *, tracker: TrackerFormat) -> Song:
    """The song a module's raw bytes hold, read by the format its own extension named.

    Raises:
        ValueError: when the bytes do not open with the named format's own tag.
    """
    match tracker:
        case TrackerFormat.XM:
            return XMModule.parse(data).song
        case TrackerFormat.IT:
            return ITModule.parse(data).song
        case TrackerFormat.MOD:
            return MODModule.parse(data).song
        case TrackerFormat.S3M:
            return S3MModule.parse(data).song
