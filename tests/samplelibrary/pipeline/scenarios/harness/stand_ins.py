from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecloud.backends import FeatureExtractor

VECTOR_SIZE: Final[int] = 512
MIDWAY_CHECKPOINT_INTERVAL: Final[int] = 2
SEED_BYTES: Final[int] = 8
PROGRAM: Final[str] = "samplelibrary"

Gate = Callable[[], None]


def _seeded(content: bytes) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(content).digest()[:SEED_BYTES], "little"))


class HeardContentExtractor:
    """Describes a sample by the frames it hears alone, so the same frames give the same vector in any process.

    It stands in for a listening model, which describes a sample the same way every time too, and
    stops at the scenario's midway gate before the sample after the first checkpoint.
    """

    def __init__(self, midway: Gate | None) -> None:
        self._midway = midway
        self._described = 0

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        self._described += 1
        if self._midway is not None and self._described == MIDWAY_CHECKPOINT_INTERVAL + 1:
            self._midway()
        return _seeded(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).standard_normal(VECTOR_SIZE)


class WordedTeacher:
    """Reads each prompt into a vector of its own words, standing in for a listening model's text tower."""

    def embed_text(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return np.stack([_seeded(text.encode("utf-8")).standard_normal(VECTOR_SIZE) for text in texts]).astype(
            np.float32
        )


def run_stand_in(command: Sequence[str], *, midway: Gate | None) -> bool:
    """Run a command whose model a scenario cannot load as the real command, with the model stood in for.

    Answers whether the command is one a stand-in exists for; every other command a scripted step
    names does nothing of its own.
    """
    words = tuple(command)
    match words[:2]:
        case ("cloud", "embed"):
            _embed(list(words[2:]), midway=midway)
        case ("cloud", "suggest"):
            _suggest(list(words[2:]))
        case _:
            return False
    return True


def _embed(argv: list[str], *, midway: Gate | None) -> None:
    # Each command is imported only by the stand-in running it, so a scripted pass loads none of them.
    # pylint: disable=import-outside-toplevel
    import samplecloud.cli
    import samplecloud.features

    extractor = HeardContentExtractor(midway)

    def stood_in_extractor(recipe: object, *, library_root: object, device: str) -> FeatureExtractor:
        return extractor

    samplecloud.cli.extractor_for = stood_in_extractor  # type: ignore[assignment]
    if midway is not None:
        samplecloud.features.EXTRACTION_CHECKPOINT_INTERVAL = MIDWAY_CHECKPOINT_INTERVAL  # type: ignore[misc]
    samplecloud.cli.main(argv, prog=f"{PROGRAM} cloud embed")


def _suggest(argv: list[str]) -> None:
    import samplecloud.suggestions.cli  # pylint: disable=import-outside-toplevel

    samplecloud.suggestions.cli.load_teacher = lambda *, device: WordedTeacher()  # type: ignore[assignment]
    samplecloud.suggestions.cli.main(argv, prog=f"{PROGRAM} cloud suggest")
