from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.waveform import fold_to_mono

DEFAULT_PROBE_FRAME_FLOOR: Final[int] = 4_000
DEFAULT_PROBE_FRAME_CEILING: Final[int] = 200_000


@dataclass(frozen=True)
class ProbeSample:
    """One real library sample together with the mono frames a measurement reads it as."""

    sample: Sample
    mono: NDArray[np.float64]


def read_probe_samples(library_root: Path, samples: tuple[Sample, ...]) -> tuple[ProbeSample, ...]:
    """Read each sample's stored audio, folded to the one channel every frequency axis analyzes."""
    return tuple(
        ProbeSample(sample=sample, mono=fold_to_mono(audio_store.read(library_root, sample).pcm)) for sample in samples
    )


def unrelated_pairs(sample_count: int, *, pair_count: int, random_seed: int) -> tuple[tuple[int, int], ...]:
    """Index pairs naming samples drawn independently, giving the scale a measurement reports against.

    Every distance a measurement reports means something only beside the distance between two
    samples that have nothing to do with each other, which is what these pairs supply.
    """
    generator = np.random.default_rng(random_seed)
    return tuple(
        (int(first), int(second))
        for first, second in (generator.choice(sample_count, size=2, replace=False) for _ in range(pair_count))
    )
