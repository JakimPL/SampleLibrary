from __future__ import annotations

import gzip
from collections.abc import Callable, Hashable
from threading import Lock
from typing import Final

CACHED_COMPRESSION_LEVEL: Final[int] = 9


class RevisionedJsonCache:
    """One serialized answer to a whole-catalog route, held for as long as the rows behind it stand.

    The cloud's points are rebuilt from five whole-table reads, a classification per sample and a
    hundred thousand models, seconds of work for an answer that changes only when a pipeline
    writes. Keeping the finished bytes, gzipped once at the best level, and checking a cheap
    revision against the tables before each use turns a request into a memory copy, while a run
    that moves the rows is picked up on the next request. Held per application and guarded by a
    lock, like the spectral vectors, since a request arrives on whichever worker thread is free.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._revision: Hashable | None = None
        self._body: bytes | None = None
        self._gzipped: bytes | None = None

    def body(self, revision: Hashable, build: Callable[[], bytes], *, gzipped: bool) -> bytes:
        """The answer at this revision, built afresh when the revision moved, in the encoding the caller takes."""
        with self._lock:
            if self._body is None or self._gzipped is None or self._revision != revision:
                self._body = build()
                self._gzipped = gzip.compress(self._body, CACHED_COMPRESSION_LEVEL)
                self._revision = revision

            return self._gzipped if gzipped else self._body
