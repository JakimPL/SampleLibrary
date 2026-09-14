from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from samplecore.auditory.sound_type import SoundType, sound_type_reading
from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono

DEFAULT_PROBE_FRAME_FLOOR: Final[int] = 4_000
DEFAULT_PROBE_FRAME_CEILING: Final[int] = 200_000


@dataclass(frozen=True)
class ProbeSample:
    """One real library sample, the mono frames a measurement reads it as, and what kind of sound it is.

    The sound type travels with the probe so every table a measurement produces can be read per
    kind: a phase estimate that serves a struck sound can fail a held one, and a figure pooled over
    both hides which.
    """

    sample: Sample
    mono: PreparedMono
    sound_type: SoundType


def read_probe_samples(library_root: Path, samples: tuple[Sample, ...]) -> tuple[ProbeSample, ...]:
    """Read each sample's stored audio, prepared exactly as every frequency axis analyzes it.

    A probe's mono is the reference every reconstruction of it is measured against, so it takes
    the same way in as the analysis and the two compare the same content. Its sound type is read
    from those frames at the rate the analysis reads them.
    """
    return tuple(_probe(sample, prepare_mono(audio_store.read(library_root, sample).pcm)) for sample in samples)


def _probe(sample: Sample, mono: PreparedMono) -> ProbeSample:
    return ProbeSample(
        sample=sample, mono=mono, sound_type=sound_type_reading(mono, sample_rate_hz=NOMINAL_WAV_RATE).sound_type
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
