from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.models.experiment import Reading
from samplecore.pitch import choose_playback_rate
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.waveform import heard_at_rate


@dataclass(frozen=True)
class Hearing:
    """One pass's reading of every sample, with the playback rates a heard-rate reading needs."""

    reading: Reading
    playback_rate_by_hash: Mapping[str, Rate]

    def hear(self, sample_hash: str, pcm: NDArray[np.float64]) -> NDArray[np.float64]:
        """The stored frames as this pass hands them to the extractor.

        Under a heard-rate reading a sample with a known playback rate comes back resampled to
        sound at the stored rate the way it sounds when played; a sample the library never plays
        keeps the nominal reading, the only one there is for it.
        """
        match self.reading:
            case Reading.NOMINAL:
                return pcm
            case Reading.HEARD_RATE:
                rate = self.playback_rate_by_hash.get(sample_hash)
                if rate is None or rate == NOMINAL_WAV_RATE:
                    return pcm
                return heard_at_rate(pcm, playback_rate_hz=float(rate), stored_rate_hz=NOMINAL_WAV_RATE)


def hearing_for(connection: Connection, reading: Reading) -> Hearing:
    """The hearing a pass asked for, its playback rates read once for the whole catalog.

    The rate of a sample is the one the library plays it at, the way the application sounds it:
    the rate its note events settle on where a pattern plays it, and otherwise the dominant rate its
    module occurrences and sample files declare.
    """
    if reading is Reading.NOMINAL:
        return Hearing(reading=reading, playback_rate_by_hash={})

    occurrence_rates = PostgresSampleRepository(connection).rates_for_every_sample()
    recorded = PostgresSamplePlaybackRateRepository(connection).list_all()
    playback_rate_by_hash: dict[str, Rate] = {}
    for sample_hash in occurrence_rates.keys() | recorded.keys():
        rate = choose_playback_rate(
            note_event_rate=recorded.get(sample_hash), occurrence_rates=occurrence_rates.get(sample_hash, ())
        )
        if rate is not None:
            playback_rate_by_hash[sample_hash] = rate
    return Hearing(reading=reading, playback_rate_by_hash=playback_rate_by_hash)
