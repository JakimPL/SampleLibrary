from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.atomic import PARTIAL_SUFFIX, write_atomically
from samplecore.storage.staging import partial_path

NEIGHBORS_FILE_NAME: Final[str] = "neighbors.npz"
COORDINATES_FILE_NAME: Final[str] = "coordinates.npy"
# The names `keep_neighbors` stores the two arrays under.
INDICES_KEY: Final[str] = "indices"
DISTANCES_KEY: Final[str] = "distances"


@dataclass(frozen=True)
class NeighborGraph:
    """Each point's nearest neighbors, the graph a layout is fitted over: their rows and their distances."""

    indices: NDArray[np.int64]
    distances: NDArray[np.float32]


@dataclass(frozen=True)
class LayoutStages:
    """The finished stages of one layout being fitted, kept in its partial so a stopped fit takes up after the last.

    A layout is named by the digest of everything it is fitted from, so stages found under that name
    are its own. Every stage is written whole, so one found is one finished.
    """

    directory: Path

    @classmethod
    def open(cls, parent: Path, *, digest: str) -> LayoutStages:
        """The stages of the layout named `digest` under `parent`, clearing the stages any other layout left there."""
        directory = partial_path(parent / digest)
        for left in parent.glob(f".*{PARTIAL_SUFFIX}"):
            if left != directory:
                shutil.rmtree(left, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory)

    def neighbors(self) -> NeighborGraph | None:
        path = self.directory / NEIGHBORS_FILE_NAME
        if not path.is_file():
            return None
        with np.load(path) as stored:
            return NeighborGraph(indices=stored[INDICES_KEY], distances=stored[DISTANCES_KEY])

    def keep_neighbors(self, graph: NeighborGraph) -> None:
        def write(stream: IO[bytes]) -> None:
            np.savez(stream, indices=graph.indices, distances=graph.distances)

        write_atomically(self.directory / NEIGHBORS_FILE_NAME, write)

    def coordinates(self) -> NDArray[np.float64] | None:
        path = self.directory / COORDINATES_FILE_NAME
        if not path.is_file():
            return None
        coordinates: NDArray[np.float64] = np.load(path)
        return coordinates

    def keep_coordinates(self, coordinates: NDArray[np.floating]) -> None:
        write_atomically(
            self.directory / COORDINATES_FILE_NAME, lambda stream: np.save(stream, coordinates.astype(np.float64))
        )

    def discard(self) -> None:
        """Remove the stages once the layout they built is written where it is read."""
        shutil.rmtree(self.directory, ignore_errors=True)
