from __future__ import annotations

from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.pitch import choose_playback_rate
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository


def resolved_playback_rates(connection: Connection, sample_hashes: list[str]) -> dict[str, Rate | None]:
    """The rate each sample is heard at, by the one rule every reader of the catalog applies.

    The note events' rate speaks first, since it is what the library really sounds the sample at;
    the occurrences' dominant rate answers for a sample the note events never reached; a sample
    with neither maps to None. Every hash asked for is present in the result.
    """
    _, occurrence_rates = PostgresSampleRepository(connection).names_and_rates_by_hash(sample_hashes)
    note_event_rates = PostgresSamplePlaybackRateRepository(connection).get_many(sample_hashes)
    return {
        sample_hash: choose_playback_rate(
            note_event_rate=note_event_rates.get(sample_hash),
            occurrence_rates=occurrence_rates.get(sample_hash, ()),
        )
        for sample_hash in sample_hashes
    }
