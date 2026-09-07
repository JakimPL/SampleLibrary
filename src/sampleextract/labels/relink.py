from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.labeling import relinked_hash
from samplecore.models.label import SampleLabel
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository


@dataclass(frozen=True)
class RelinkSummary:
    """What one relink pass did with the labels whose sample the catalog no longer holds."""

    checked: int
    stale: int
    relinked: int
    unresolved: tuple[SampleLabel, ...]


def relink_labels(connection: Connection) -> RelinkSummary:
    """Point every label whose sample the catalog has lost back at the slot it was chosen from.

    A sample's hash follows from how this project hashes audio, so changing that leaves a label
    naming a hash the catalog knows nothing about. Each label also carries the module slot it was
    found in, and reading that slot's current occupant is what recovers the sample it meant. Labels
    whose sample is still catalogued are left exactly as they are, so this is safe to run at any
    time.

    A label whose module or slot is gone from the catalog too comes back under ``unresolved``, for a
    person to decide about; it stays on file untouched.
    """
    repository = PostgresSampleLabelRepository(connection)
    labels = repository.list_all()
    catalogued = PostgresSampleRepository(connection).get_many([label.sample_hash for label in labels])
    stale = tuple(label for label in labels if label.sample_hash not in catalogued)

    recovered: list[tuple[str, SampleLabel]] = []
    unresolved: list[SampleLabel] = []
    for label in stale:
        current_hash = relinked_hash(connection, label)
        if current_hash is None:
            unresolved.append(label)
        else:
            recovered.append((label.sample_hash, label.model_copy(update={"sample_hash": current_hash})))

    with start_batch(connection):
        repository.delete_many(tuple(previous_hash for previous_hash, _ in recovered))
        repository.upsert_many(tuple(label for _, label in recovered))

    return RelinkSummary(checked=len(labels), stale=len(stale), relinked=len(recovered), unresolved=tuple(unresolved))
