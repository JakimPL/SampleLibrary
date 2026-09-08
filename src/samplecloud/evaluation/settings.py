from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

DEFAULT_RANDOM_SEED: Final[int] = 0
DEFAULT_PROBE_COUNT: Final[int] = 200
DEFAULT_NEIGHBOR_COUNT: Final[int] = 5
DEFAULT_FOLD_COUNT: Final[int] = 5
DEFAULT_SEMITONE_OFFSETS: Final[tuple[float, ...]] = (
    -24.0,
    -17.0,
    -12.0,
    -7.0,
    -5.0,
    -2.0,
    2.0,
    5.0,
    7.0,
    12.0,
    17.0,
    24.0,
)


@dataclass(frozen=True)
class EvaluationSettings:
    """How one evaluation pass is run: the draws it makes and the folds it scores over.

    Every metric reads the same settings, so one seed fixes every split and every draw and a second
    run of the same pass reproduces every number. The offsets form a fixed mirrored grid rather than
    a random draw, which is what lets two runs compare offset by offset.
    """

    random_seed: int = DEFAULT_RANDOM_SEED
    probe_count: int = DEFAULT_PROBE_COUNT
    neighbor_count: int = DEFAULT_NEIGHBOR_COUNT
    fold_count: int = DEFAULT_FOLD_COUNT
    semitone_offsets: tuple[float, ...] = field(default=DEFAULT_SEMITONE_OFFSETS)

    def __post_init__(self) -> None:
        if self.fold_count < 2:
            raise ValueError(f"an evaluation pass needs at least two folds, got {self.fold_count}")
        if self.neighbor_count < 1:
            raise ValueError(f"an evaluation pass needs at least one neighbor, got {self.neighbor_count}")
        if self.probe_count < 1:
            raise ValueError(f"an evaluation pass needs at least one probe, got {self.probe_count}")
        if not self.semitone_offsets:
            raise ValueError("an evaluation pass needs at least one semitone offset to retune by")
