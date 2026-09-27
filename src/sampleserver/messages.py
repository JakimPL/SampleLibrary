from __future__ import annotations

from typing import Final

# What the served API tells a person when it refuses, in the words a page shows them. Where the
# serving policy names internals, a refusal carries the file or address behind it instead.

NOT_ADMITTED: Final[str] = "This library can't be opened from here."
UNREADABLE_AUDIO: Final[str] = "This sample's audio can't be read right now."
MORPH_UNAVAILABLE: Final[str] = "Morphs can't be played right now."
MORPH_TIMED_OUT: Final[str] = "This morph took too long to make."
MORPH_REFUSED: Final[str] = "This morph can't be made."
CURATION_WITHHELD: Final[str] = "This library shows no ratings or favorites."
NOT_FOUND: Final[str] = "Not Found"

SERVE_REFUSES_PUBLIC: Final[str] = (
    "This config serves the library to anyone on the internet, which `samplelibrary site` does, with its "
    "renderer and its visitor limits. Start it that way."
)
HOST_BEYOND_EXPOSURE: Final[str] = (
    'This config serves the library on this computer alone, so it listens on 127.0.0.1. Set exposure = "network" '
    "under [server] to let other devices on your network open it."
)
