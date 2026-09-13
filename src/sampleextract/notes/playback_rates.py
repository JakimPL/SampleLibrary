from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.pitch import dominant_playback_rate, tally_playback_rates
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository


def record_playback_rates(connection: Connection) -> int:
    """Fold every note event on file into one effective playback rate per sample and write it down.

    A rate a sample is really heard at follows from an occurrence's own rate and the key struck
    against it, so answering it means reading the whole note-event table -- a minute of database work
    over tens of millions of rows. Taking it once, here beside the pass that writes those events,
    leaves every reader a per-sample lookup. The whole answer is replaced at once, so the rates on
    file always come from one reading of the catalog.

    Returns:
        How many samples a rate was recorded for.
    """
    tallies: dict[str, Counter[Rate]] = defaultdict(Counter)
    for sample_hash, usage in PostgresNoteEventRepository(connection).note_usage_for_every_sample():
        tallies[sample_hash].update(tally_playback_rates((usage,)))

    rate_by_hash = {
        sample_hash: rate
        for sample_hash, tally in tallies.items()
        if (rate := dominant_playback_rate(tally)) is not None
    }
    with start_batch(connection):
        PostgresSamplePlaybackRateRepository(connection).replace_all(rate_by_hash)

    return len(rate_by_hash)
