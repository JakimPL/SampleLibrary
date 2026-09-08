from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.anchoring import relinked_hash
from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class RelinkSummary:
    """What one relink pass did with the annotations whose sample the catalog no longer holds."""

    checked: int
    stale: int
    relinked: int
    unresolved: tuple[SampleAnnotation, ...]


def relink_annotations(connection: Connection) -> RelinkSummary:
    """Point every annotation whose sample the catalog has lost back at the slot it was chosen from.

    A sample's hash follows from how this project hashes audio, so changing that leaves an
    annotation naming a hash the catalog knows nothing about. Each annotation also carries the
    module slot it was found in, and reading that slot's current occupant is what recovers the
    sample it meant. Annotations whose sample is still cataloged are left exactly as they are, so
    this is safe to run at any time.

    An annotation whose module or slot is gone from the catalog too comes back under
    ``unresolved``, for a person to decide about; it stays on file untouched.
    """
    repository = PostgresSampleAnnotationRepository(connection)
    annotations = repository.list_all()
    cataloged = PostgresSampleRepository(connection).get_many([annotation.sample_hash for annotation in annotations])
    stale = tuple(annotation for annotation in annotations if annotation.sample_hash not in cataloged)

    recovered: list[tuple[str, SampleAnnotation]] = []
    unresolved: list[SampleAnnotation] = []
    for annotation in stale:
        current_hash = relinked_hash(connection, annotation)
        if current_hash is None:
            unresolved.append(annotation)
        else:
            recovered.append((annotation.sample_hash, annotation.model_copy(update={"sample_hash": current_hash})))

    with start_batch(connection):
        repository.delete_many(tuple(previous_hash for previous_hash, _ in recovered))
        repository.replace_many(tuple(annotation for _, annotation in recovered))

    return RelinkSummary(
        checked=len(annotations), stale=len(stale), relinked=len(recovered), unresolved=tuple(unresolved)
    )
