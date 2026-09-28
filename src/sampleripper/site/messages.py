from __future__ import annotations

from typing import Final

# What `sampleripper site` says as it refuses to start, or as it starts, each a sentence the person deploying reads.

NOT_PUBLIC: Final[str] = (
    'A site serves the library to anyone. Set exposure = "public" under [server], with its [server.visitors] limits.'
)
NO_PORT: Final[str] = "Name the port the site listens on in $PORT, as a hosting platform does."
BAD_PORT: Final[str] = "$PORT names no port a server can listen on: {value!r}."
NO_READER: Final[str] = (
    "Name the role the site reads the catalog as in SAMPLERIPPER_SERVER_DATABASE_URL, the reader a publication creates."
)
WEAK_READER_PASSWORD: Final[str] = "The reader's password is shorter than {length} characters. Give it a generated one."
CREDENTIAL_BEYOND_READER: Final[str] = (
    "{name} names a connection that may change the catalog, which a site holds none of. Remove it from the "
    "site's configuration."
)
RENDERER_BEYOND_THIS_COMPUTER: Final[str] = (
    "The morph renderer of a site listens on this computer alone. Set [inference] url to a loopback address."
)
PORT_TAKEN_BY_RENDERER: Final[str] = "$PORT is the port the morph renderer listens on. Give [inference] url another."
UNREADABLE_AUDIO_STORE: Final[str] = "The site can't read its audio store at {path}. Give the site's user access to it."
NO_AUDIO: Final[str] = (
    "The site finds no audio at {path}, so no sample plays yet. Upload the publication's objects there; samples "
    "play as soon as they arrive."
)
RENDERER_DID_NOT_START: Final[str] = "The morph renderer did not start answering within {seconds:g} seconds."
RENDERER_ENDED_AT_START: Final[str] = "The morph renderer ended as it started; its output above says why."
RENDERER_ENDED: Final[str] = "The morph renderer ended with status {status}, so the site stops too."
