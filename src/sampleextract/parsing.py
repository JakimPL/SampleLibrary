from __future__ import annotations

from trackmod.core.songs.song import Song
from trackmod.trackers.it.module import ITModule
from trackmod.trackers.xm.module import XMModule

from samplecore.models.tracker import TrackerFormat


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
