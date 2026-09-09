from __future__ import annotations

from datetime import datetime
from threading import Lock

from sqlalchemy import Connection

from samplecore.spectral_distance import SpectralVectors
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository

_Revision = tuple[int, datetime | None]


class SpectralVectorCache:
    """One parsed copy of the catalog's spectral vectors, held for as long as it describes it.

    Every nearest-neighbor search measures the whole catalog, and reading those vectors back means
    parsing a couple of hundred megabytes of stored text -- seconds of work, repeated per request,
    for an answer that changes only when an embedding pass runs. Keeping the parsed matrix and
    checking a two-number revision against the table before each use turns that into one cheap
    query, while an embedding run that replaces the rows is picked up on the next request.

    Held per application rather than per module, so a test's own app starts with nothing cached, and
    guarded by a lock because a request arrives on whichever worker thread is free.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._revision: _Revision | None = None
        self._vectors: SpectralVectors | None = None

    def vectors(self, connection: Connection) -> SpectralVectors:
        """The catalog's vectors as one matrix, parsed afresh whenever the stored rows have moved on."""
        repository = PostgresSampleSpectralFeatureRepository(connection)
        revision = repository.revision()
        with self._lock:
            if self._vectors is None or self._revision != revision:
                self._vectors = repository.vectors()
                self._revision = revision

            return self._vectors
