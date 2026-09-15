from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.listening.pairs import CatalogPair, DrawnPair, RetunedPair
from samplemorph.pipeline import common_rate, read_heard_sample
from samplemorph.routes.route import HeardMono, hear_in_frame


class PairSampleMissing(ValueError):
    """Raised when a pair names a sample the catalog holds no sample under."""


@dataclass(frozen=True)
class OriginalSound:
    """One end of a pair as the library plays it: its prepared frames and the rate they are played at."""

    mono: PreparedMono
    rate_hz: float


@dataclass(frozen=True)
class PathReference:
    """The sound a path should reach at one weight, heard in the pair's frame."""

    weight: float
    heard: HeardMono


@dataclass(frozen=True)
class HeardPair:
    """A drawn pair read from the catalog: both ends as the library plays them, and both heard in the pair's frame.

    `references` holds, for a sample heard at two rates, that sample heard at the rate between them
    at every weight strictly between the ends, and is empty for a pair of two samples.
    """

    pair: DrawnPair
    first_original: OriginalSound
    second_original: OriginalSound
    first: HeardMono
    second: HeardMono
    references: tuple[PathReference, ...]

    @property
    def rate_hz(self) -> float:
        return self.first.rate_hz


def read_heard_pair(
    connection: Connection, audio: SampleAudio, pair: DrawnPair, *, weights: tuple[float, ...]
) -> HeardPair:
    """Read both ends of a pair and hear them in the frame of the higher of their rates.

    Raises:
        PairSampleMissing: the pair names a sample the catalog holds no sample under.
        ValueError: the catalog knows no playback rate for a sample of a pair of two samples.
        SampleUnavailableError: a sample lives only in sample files, and none of them holds it now.
    """
    match pair:
        case CatalogPair():
            first = read_heard_sample(connection, audio, _sample(connection, pair.first.sample_hash))
            second = read_heard_sample(connection, audio, _sample(connection, pair.second.sample_hash))
            return _heard(pair, pcm=(first.pcm, second.pcm), rates_hz=(first.rate_hz, second.rate_hz), weights=())
        case RetunedPair():
            pcm = audio.read(_sample(connection, pair.sample.sample_hash)).pcm
            return _heard(pair, pcm=(pcm, pcm), rates_hz=(pair.first_rate_hz, pair.second_rate_hz), weights=weights)


def _heard(
    pair: DrawnPair,
    *,
    pcm: tuple[NDArray[np.float64], NDArray[np.float64]],
    rates_hz: tuple[float, float],
    weights: tuple[float, ...],
) -> HeardPair:
    """The pair heard in its frame, with a reference at each of `weights` strictly between the ends."""
    frame_rate_hz = common_rate(*rates_hz)
    return HeardPair(
        pair=pair,
        first_original=OriginalSound(mono=prepare_mono(pcm[0]), rate_hz=rates_hz[0]),
        second_original=OriginalSound(mono=prepare_mono(pcm[1]), rate_hz=rates_hz[1]),
        first=hear_in_frame(pcm[0], rate_hz=rates_hz[0], target_rate_hz=frame_rate_hz),
        second=hear_in_frame(pcm[1], rate_hz=rates_hz[1], target_rate_hz=frame_rate_hz),
        references=tuple(
            PathReference(
                weight=weight,
                heard=hear_in_frame(
                    pcm[0],
                    rate_hz=rates_hz[0] ** (1.0 - weight) * rates_hz[1] ** weight,
                    target_rate_hz=frame_rate_hz,
                ),
            )
            for weight in weights
            if 0.0 < weight < 1.0
        ),
    )


def _sample(connection: Connection, sample_hash: str) -> Sample:
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise PairSampleMissing(f"the catalog holds no sample {sample_hash}")
    return sample
