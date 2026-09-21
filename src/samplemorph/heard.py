from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.playback_rates import resolved_playback_rates
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio


@dataclass(frozen=True)
class HeardSample:
    """One catalog sample as the library plays it: its stored frames, and the rate they are read at."""

    sample: Sample
    pcm: NDArray[np.float64]
    rate_hz: float


def common_rate(first_rate_hz: float, second_rate_hz: float) -> float:
    """The rate a pair is carried into one frame at: the higher of the two.

    The faster sample keeps every band it has and the slower one gains frames and loses nothing,
    which no rate between the two could promise for the faster one.
    """
    return max(first_rate_hz, second_rate_hz)


def read_heard_sample(connection: Connection, audio: SampleAudio, sample: Sample) -> HeardSample:
    """Read one cataloged sample with the rate the application plays it at.

    The audio a reader gets states a nominal rate rather than a measured one, so the rate is read
    from the catalog by the one rule every reader applies: what the note events say first, the
    dominant rate the occurrences and sample files declare after.

    Raises:
        ValueError: the catalog holds no occurrence or file of this sample, so no playback rate is known.
        SampleUnavailableError: the sample lives only in sample files, and none of them holds it now.
    """
    rate = resolved_playback_rates(connection, [sample.hash])[sample.hash]
    if rate is None:
        raise ValueError(f"sample {sample.hash} has no cataloged occurrence, so its playback rate is unknown")

    return HeardSample(sample=sample, pcm=audio.read(sample).pcm, rate_hz=float(rate))


class SampleNotCataloged(ValueError):
    """Raised when a command names a sample hash the catalog holds no sample under."""


def require_sample(connection: Connection, sample_hash: str) -> Sample:
    """Look one sample up by hash.

    Raises:
        SampleNotCataloged: the catalog holds no sample under that hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise SampleNotCataloged(f"the catalog holds no sample {sample_hash}")

    return sample
